#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020 Kondo Taiki
#
# This file is part of "pgmaster2".
#
# "pgmaster2" is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# "pgmaster2" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "pgmaster2".  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import errno
import psycopg2
import datetime, time
import fcntl
import configparser
import html
from git import *
from flask import *

import pg_connection

app = Flask(__name__)
pg_conn = None

@app.route('/')
def root():
  """
  root() - Generate page for /
    No argument required.
  """
  projects = []

  conn = pg_conn.connect()
  try:
    with conn.cursor() as cursor:
      cursor.execute(
        u"""SELECT
          distinct project
        FROM
          branch_info;
      """)

      rows = cursor.fetchall()
      if len(rows) <= 0:
        raise FileNotFoundError

      for (p,) in rows:
        p_info = {
          'name' : p,
          'url'  : url_for('project', project = p)
        }
        projects.append(p_info)
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    print(e)
    abort(500)
  finally:
    pg_conn.close(conn)

  return render_template('hello.html.jinja2', projects = projects)

@app.route('/p/<project>/')
def project(project):
  """
  project() - Generate page for /p/<project>/
    project : project name
  """
  branches = []

  conn = pg_conn.connect()
  try:
    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
        branch
      FROM
        branch_info
      WHERE
        project = %s;""",
      [project]
      )
      for (b,) in cursor.fetchall():
        b_info = {
          'name' : b,
          'url'  : url_for(
            'branch',
            project=project,
            branch=b
          )
        }
        branches.append(b_info)
  except Exception as e:
    print(e)
    abort(500)
  finally:
    pg_conn.close(conn)

  return render_template('project.html.jinja2',
    project = project,
    branches = branches)

@app.route('/p/<project>/b/<branch>/')
def branch(project, branch):
  """
  branch() - Generate page for /p/<project>/b/<branch>/
    project : project name
    branch  : branch name
  """
  page = 1  # page number (must be greater than 0)
  num = 20  # count of commits in each page (must be greater than 1)

  try:
    if request.args.get('page') is not None:
      if int(request.args.get('page')) <= 0:
        raise ValueError
      page = int(request.args.get('page'))

    if request.args.get('num') is not None:
      if int(request.args.get('num')) <= 1:
        raise ValueError
      num = int(request.args.get('num'))
  except ValueError as e:
    abort(403)
  except Exception as e:
    print(e)
    abort(500)

  if request.args.get('page') is None or request.args.get('num') is None:
    return redirect(
      url_for('branch', project = project, branch = branch, page = page, num = num)
    )

  urls = {
    'page' : page,
    'prev' : url_for(
      'branch', project = project, branch = branch,
      page = page - 1,
      num = num
      ),
    'next' : url_for(
      'branch', project = project, branch = branch,
      page = page + 1,
      num = num
      )
  }
  commits = []
  fd = None
  conn = pg_conn.connect()

  try:
    # Connect to git repository
    fd = open(u'git/.lock.' + project, 'r')
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # LOCK!
    repo = Repo(u'git/' + project + u'.git')

    if not repo.bare:
      raise FileNotFoundError

    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
        b.commitid,
        b.scommitid,
        b.commitdate_l,
        b.timezone_int,
        i.updatetime
      FROM
        _branch b
        LEFT JOIN _investigation i USING (project, branch, commitid)
      WHERE
        project = %s and branch = %s
      ORDER BY
        commitdate DESC, scommitid
      OFFSET %s
      LIMIT %s""",
      [project, branch, (page - 1) * num, num])

      rows = cursor.fetchall()
      if len(rows) <= 0:
        raise FileNotFoundError
      
      for c in rows:
        commit = repo.commit(c[0])
        c_info = {
          'id'      : c[0],
          'sid'     : c[1],
          'date'    : c[2],
          'tz'      : c[3],
          'updated' : c[4],
          'summary' : commit.summary,
          'author'  : commit.author,
          'url'     : url_for(
            'investigate',
            project = project,
            branch = branch,
            commitid = c[0]
          )
        }
        commits.append(c_info)

  except OSError as e:
    # Can't aquire lock
    if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
      abort(503)
    else:
      abort(500)
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    print(e)
    abort(500)
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None
    pg_conn.close(conn)

  return render_template(
    'branch.html.jinja2',
    project = project,
    branch = branch,
    commits = commits,
    urls = urls
  )

@app.route('/p/<project>/b/<branch>/c/<commitid>/')
def investigate(project, branch, commitid):
  """
  investigate() - Generate page for /p/<project>/b/<branch>/c/<commitid>
    project : project name
    branch  : branch name
    commitid: commitid
  """

  def make_patch(src, dst):
    diffs = []
    for d in src.diff(dst, create_patch = True):
      a_path = 'a/%s' % d.a_rawpath.decode('utf-8') if d.a_rawpath is not None else '/dev/null'
      b_path = 'b/%s' % d.b_rawpath.decode('utf-8') if d.b_rawpath is not None else '/dev/null'
      patch_str = (
        u'--- %s\n'
        u'+++ %s\n'
        u'\n'
        u'%s'
      ) % (
        a_path,
        b_path,
        d.diff.decode('utf-8')
      )
      # Append Sanitized strings
      diffs.append(html.escape(patch_str))

    return diffs
  
  def make_html_message(message):
    # Split lines (and chop CR and LF)
    lines = html.escape(message).splitlines()
    result = u'<br>\n'.join(lines)
    return result

  fd = None
  conn = pg_conn.connect()

  try:
    # Connect to git repository
    fd = open(u'git/.lock.' + project, 'r')
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # LOCK!
    repo = Repo(u'git/' + project + u'.git')

    if not repo.bare:
      raise FileNotFoundError

    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
        b.scommitid,
        b.commitdate_l,
        b.timezone_int,
        i.updatetime,
        i.snote,
        i.note,
        i.analysis
      FROM
        _branch b
        LEFT JOIN _investigation i USING (project, branch, commitid)
      WHERE
        project = %s and branch = %s and commitid = %s""",
      [project, branch, commitid]
      )

      c = cursor.fetchone()
      commit = repo.commit(commitid)
      p_commit = commit.parents[0]
      c_info = {
        'id'         : commitid,
        'sid'        : c[0],
        'date'       : c[1],
        'tz'         : c[2],
        'updated'    : c[3],
        'summary'    : commit.summary,
        'message'    : make_html_message(commit.message),
        'author'     : commit.author,
        'diffs'      : make_patch(p_commit, commit),
        'snote'      : c[4] if c[4] is not None else u'',
        'note'       : c[5] if c[5] is not None else u'',
        'analysis'   : c[6] if c[6] is not None else u'',
        'invest_url' : url_for(
          'investigate_modify',
          project = project,
          branch = branch,
          commitid = commitid
        )
      }

  except OSError as e:
    # Can't aquire lock
    if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
      abort(503)
    else:
      abort(500)
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    print(e)
    abort(500)
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None
    pg_conn.close(conn)

  return render_template(
    'investigate.html.jinja2',
    project = project,
    branch = branch,
    commit = c_info
  )

@app.route('/p/<project>/b/<branch>/c/<commitid>/modify', methods = ['POST'])
def investigate_modify(project, branch, commitid):
  """
  investigate_modify() - Insert or Update a result of investigation.
    project : project name
    branch  : branch name
    commitid: commitid
  """
  form_data = {}
  form_data.update(request.form)  # Make copy
  try:
    if len(form_data['snote']) <= 0:
      raise ValueError
    else:
      #form_data['snote'] = u'\n'.join(form_data['snote'].striplines())
      pass

    if len(form_data['note']) <=0:
      raise ValueError
    else:
      form_data['note'] = u'\n'.join(form_data['note'].splitlines())

    if len(form_data['analysis']) <=0:
      pass
    else:
      form_data['analysis'] = u'\n'.join(form_data['analysis'].splitlines())
  except Exception as e:
    print(e)
    abort(403)

  conn = pg_conn.connect()

  try:
    with conn.cursor() as cursor:
      cursor.execute(u"""INSERT INTO _investigation (
          project,
          branch,
          commitid,
          snote,
          note,
          analysis
        ) VALUES (
          %s,
          %s,
          %s,
          %s,
          %s,
          %s
        ) ON CONFLICT ON CONSTRAINT _investigation_pkey
        DO UPDATE SET
          snote = %s,
          note = %s,
          analysis = %s,
          updatetime = now()""",
        [
          project,
          branch,
          commitid,
          form_data['snote'],
          form_data['note'],
          form_data['analysis'],
          form_data['snote'],  # for UPSERT
          form_data['note'],
          form_data['analysis']
        ]
      )
    conn.commit()
  except psycopg2.Error as e:
    abort(500)
  finally:
    pg_conn.close(conn)

  return redirect(
    url_for(
      'investigate',
      project = project,
      branch = branch,
      commitid = commitid
    )
  )

if __name__ == "__main__":
  # Read configuration file
  config_ini = configparser.ConfigParser()
  config_ini.read('pgmaster.ini', encoding = 'utf-8')
  dbinfo = config_ini['PGMASTER']

  # Connect to the database
  pg_conn = pg_connection.pg_connection(
    server = dbinfo['Server'],
    port = dbinfo['Port'],
    database = dbinfo['Database'],
    user = dbinfo['User'],
    password = dbinfo['Password'],
    pooling = int(dbinfo['Pooling'])
  )

  app.run(
    host = '0.0.0.0',
    debug = True
  )
