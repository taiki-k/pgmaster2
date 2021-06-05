#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020-2021 Kondo Taiki
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
import datetime, time
import fcntl
import configparser
import traceback
import html
from git import *
from flask import *

import pg_connection
import webapi_v1

app = Flask(__name__)
# Register WebAPI v1
app.register_blueprint(webapi_v1.api, url_prefix=u'/api/v1')

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
    abort(500, traceback.format_exc())
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
    abort(500, traceback.format_exc())
  finally:
    pg_conn.close(conn)

  return render_template('project.html.jinja2',
    project = project,
    branches = branches)

def validate_page_number(request_args, page = 1, num = 20):
  """
  page : page number (must be greater than 0)
  num  : count of commits in each page (must be greater than 1)
  """

  if request_args.get('page') is not None:
    if int(request.args.get('page')) <= 0:
      raise ValueError
    page = int(request.args.get('page'))

  if request_args.get('num') is not None:
    if int(request.args.get('num')) <= 1:
      raise ValueError
    num = int(request.args.get('num'))
  
  return (page, num)

@app.route('/p/<project>/b/<branch>/')
def branch(project, branch):
  """
  branch() - Generate page for /p/<project>/b/<branch>/
    project : project name
    branch  : branch name
  """
  page = None
  num = None

  try:
    (page, num) = validate_page_number(request.args)
  except ValueError as e:
    abort(403)
  except Exception as e:
    abort(500, traceback.format_exc())

  if request.args.get('page') is None or request.args.get('num') is None:
    return redirect(
      url_for('branch', project = project, branch = branch, page = page, num = num)
    )

  commits = []
  max_page = 0
  fd = None
  conn = pg_conn.connect()

  try:
    # Connect to git repository
    fd = open(u'git/.lock.' + project, 'r')
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # LOCK!
    repo = Repo(u'git/' + project + u'.git')

    if not repo.bare:
      raise FileNotFoundError

    # Calcurate max number of page.
    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
        count(*)
      FROM
        _branch
      WHERE
        project = %s AND branch = %s
      """,
      [project, branch])

      rows = cursor.fetchall()
      if len(rows) <= 0:
        raise FileNotFoundError

      # This returns only 1 row with 1 column.
      rows_count = rows[0][0]
      if rows_count <= 0:
        raise FileNotFoundError
      max_page = rows_count // num + (0 if rows_count % num == 0 else 1)

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
        project = %s AND branch = %s
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
      abort(500, traceback.format_exc())
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    abort(500, traceback.format_exc())
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None
    pg_conn.close(conn)

  urls = {
    'page' : page,
    'num'  : num,
    'max_page' : max_page,
    'baseURL' : url_for('branch', project = project, branch = branch),
  }

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
    import re
    regex_patterns = [
      {  # for Web link (http(s)://...)
        'pattern' : re.compile(r"https?://[\w!?/+\-_~=;.,*&@#$%()'[\]]+"),
        'replace' : u"<a href=\"%s\" target=\"_blank\">%s</a>"
      },
      {  # for CVE (link to MITRE)
        'pattern' : re.compile(r"CVE-[0-9]{4}-[0-9]+"),
        'replace' : u"<a href=\"https://cve.mitre.org/cgi-bin/cvename.cgi?name=%s\" target=\"_blank\">%s</a>"
      }
    ]
    ptrn_commitid = re.compile(r"[0-9a-fA-F]{6,40}")

    lines = []
    # Split lines (and chop CR and LF)
    msg_lines = html.escape(message).splitlines()
    # Create links
    for line in msg_lines:
      for ptrn in regex_patterns:
        if ptrn['pattern'].search(line):
          line = re.sub(
            ptrn['pattern'],
            lambda x : ptrn['replace'] % (x.group(0), x.group(0)),
            line
          )
          break
        else:
          pass
      else:
        if ptrn_commitid.search(line):
          line = re.sub(
            ptrn_commitid,
            lambda x : (
              u"<a href=\"%s\" target=\"_blank\">%s</a>" % (
                url_for('search_commit', project = project, commitid = x.group(0)),
                x.group(0)
              ) if ( # Recheck if this part is a valid commit ID.
                (    # Check the charactor BEFORE matched part.
                  (x.start(0) == 0) or (
                    (x.start(0) > 0) and re.match(r'[ ({<"\'[]', x.string[x.start(0) - 1])
                  )
                ) and ( # Check the charactor AFTER matched part.
                  (x.end(0) == len(x.string)) or (
                    (x.end(0) < len(x.string)) and re.match(r'[ )}>"\'\].,!:;]', x.string[x.end(0)])
                  )
                )
              ) else x.group(0)
            ), # end of lambda x
            line
          ) # end of re.sub

      lines.append(line)

    result = u'<br>\n'.join(lines)
    return result
  # end of function

  urls = {
    'backpatch' : url_for(
      'search_backpatch',
      project = project,
      branch = branch,
      commitid = commitid
    )
  }

  fd = None
  conn = pg_conn.connect()

  # We have to replace from following chars to escaped one,
  # because these will be inserted as JSON string.
  trans_escaped = str.maketrans({
      '"' : r'\"',
      '\\' : r'\\',
      '\n' : r'\n'
    })

  try:
    # Connect to git repository
    fd = open(u'git/.lock.' + project, 'r')
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # LOCK!
    repo = Repo(u'git/' + project + u'.git')

    if not repo.bare:
      raise FileNotFoundError

    # Get commit information
    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
          b.scommitid,
          b.commitdate_l,
          b.timezone_int,
          i.updatetime,
          i.snote,
          i.note,
          i.analysis,
          i.keywords
        FROM
          _branch b
          LEFT JOIN _investigation i USING (project, branch, commitid)
        WHERE
          project = %s AND branch = %s AND commitid = %s""",
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
        'snote'      : c[4].translate(trans_escaped) if c[4] is not None else u'',
        'note'       : c[5].translate(trans_escaped) if c[5] is not None else u'',
        'analysis'   : c[6].translate(trans_escaped) if c[6] is not None else u'',
        'keywords'   : c[7] if c[7] is not None else [],
        'invest_url' : url_for(
          'investigate_modify',
          project = project,
          branch = branch,
          commitid = commitid
        )
      }
    # End of "with conn.cursor()"

    # Get keywords
    # TODO: Commonalize logic between here and WebAPI.
    keywords = []
    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
          array_agg(DISTINCT k)
        FROM (
          SELECT
            UNNEST(keywords) AS k
          FROM
            _investigation i
          WHERE
            project = %s AND keywords IS NOT NULL
          ORDER BY
            k
        ) AS t""",
        [project]
      )

      c = cursor.fetchone()
      keywords.extend(c[0] if c[0] is not None else [])

  except OSError as e:
    # Can't aquire lock
    if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
      abort(503)
    else:
      abort(500, traceback.format_exc())
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    abort(500, traceback.format_exc())
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
    commit = c_info,
    keywords = keywords,
    urls = urls
  )

@app.route('/p/<project>/b/<branch>/c/<commitid>/modify', methods = ['POST'])
def investigate_modify(project, branch, commitid):
  """
  [ABOLISHED] investigate_modify() - Insert or Update a result of investigation.
    project : project name
    branch  : branch name
    commitid: commitid
  This procedure is ABOLISHED and DO NOT USE. Use WebAPI instead.
  """
  abort(410, traceback.format_exc())

@app.route('/p/<project>/c/<commitid>/')
def search_commit(project, commitid):
  """
  search_commit() - Generate page for /p/<project>/c/<commitid>/
    project  : project name
    commitid : a part of commit id search for
  """
  # Check if specified commit id is valid.
  if len(commitid) < 6 or 40 < len(commitid):
    # Return "Not found"
    abort(404)

  page = None
  num = None

  try:
    (page, num) = validate_page_number(request.args)
  except ValueError as e:
    abort(403)
  except Exception as e:
    abort(500, traceback.format_exc())

  urls = None

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
      search_commitid = commitid if len(commitid) == 40 else u'%s%%' % (commitid)
      query_string = u"""SELECT
        b.commitid,
        b.scommitid,
        b.commitdate_l,
        b.timezone_int,
        i.updatetime,
        b.branch
      FROM
        _branch b
        LEFT JOIN _investigation i USING (project, branch, commitid)
      WHERE
        project = %s AND """
      query_string += u"commitid = %s " if len(commitid) == 40 else u"commitid like %s "
      query_string += u"""ORDER BY
        commitdate DESC, scommitid
      OFFSET %s
      LIMIT %s"""
      cursor.execute(query_string,
        [project, search_commitid, (page - 1) * num, num]
      )

      rows = cursor.fetchall()
      if len(rows) <= 0 and page == 1:
        raise FileNotFoundError

      # If found only 1 commit, redirect to this commit to feel lucky.
      if len(rows) == 1 and page == 1:
        return redirect(
          url_for(
            'investigate',
            project = project,
            branch = rows[0][5],
            commitid = rows[0][0]
          )
        )
      
      for c in rows:
        commit = repo.commit(c[0])
        c_info = {
          'id'      : c[0],
          'sid'     : c[1],
          'date'    : c[2],
          'tz'      : c[3],
          'updated' : c[4],
          'branch'  : c[5],
          'summary' : commit.summary,
          'author'  : commit.author,
          'url'     : url_for(
            'investigate',
            project = project,
            branch = c[5],
            commitid = c[0]
          )
        }
        commits.append(c_info)

  except OSError as e:
    # Can't aquire lock
    if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
      abort(503)
    else:
      abort(500, traceback.format_exc())
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    abort(500, traceback.format_exc())
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None
    pg_conn.close(conn)

  return render_template(
    'search_commit.html.jinja2',
    project = project,
    commitid = commitid,
    commits = commits,
    urls = urls
  )

@app.route('/p/<project>/b/<branch>/c/<commitid>/backpatch')
def search_backpatch(project, branch, commitid):
  """
  search_backpatch() - Generate page for /p/<project>/b/<branch>/c/<commitid>/backpatch
    project : project name
    branch  : branch name
    commitid: commitid
  """
  # Check if specified commit id is valid.
  if len(commitid) != 40:
    # Commit id is invalid. Return "Not found".
    abort(404)

  page = None
  num = None

  try:
    (page, num) = validate_page_number(request.args)
  except ValueError as e:
    abort(403)
  except Exception as e:
    abort(500, traceback.format_exc())

  urls = None

  commits = []
  this_commit = {
    'id'  : commitid,
    'sid' : None
  }
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
          a.commitid,
          a.scommitid,
          a.commitdate_l,
          a.timezone_int,
          i.updatetime,
          a.branch
        FROM
          _branch a
          JOIN _branch b ON (a.project = b.project)
          LEFT JOIN _investigation i ON (a.project = i.project AND a.branch = i.branch AND a.commitid = i.commitid)
        WHERE
          a.commitdate BETWEEN b.commitdate-'5 minutes'::interval and b.commitdate+'5 minutes'::interval AND
          b.project = %s AND
          b.branch = %s AND
          b.commitid = %s
        ORDER BY
          a.commitdate DESC, a.scommitid
        OFFSET %s
        LIMIT %s""",
        [project, branch, commitid, (page - 1) * num, num]
      )

      rows = cursor.fetchall()
      if len(rows) <= 0 and page == 1:
        raise FileNotFoundError

      for c in rows:
        commit = repo.commit(c[0])
        c_info = {
          'id'      : c[0],
          'sid'     : c[1],
          'date'    : c[2],
          'tz'      : c[3],
          'updated' : c[4],
          'branch'  : c[5],
          'summary' : commit.summary,
          'author'  : commit.author,
          'url'     : url_for(
            'investigate',
            project = project,
            branch = c[5],
            commitid = c[0]
          )
        }
        commits.append(c_info)
        if c_info['id'] == commitid:
          this_commit['sid'] = c_info['sid']

  except OSError as e:
    # Can't aquire lock
    if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
      abort(503)
    else:
      abort(500, traceback.format_exc())
  except FileNotFoundError as e:
    abort(404)
  except Exception as e:
    abort(500, traceback.format_exc())
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None
    pg_conn.close(conn)

  return render_template(
    'search_backpatch.html.jinja2',
    project = project,
    branch = branch,
    commit = this_commit,
    commits = commits,
    urls = urls
  )

@app.before_first_request
def prepare_app():
  global pg_conn

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

  # Register pg_connection instance to WebAPI
  webapi_v1.pg_conn = pg_conn


if __name__ == "__main__":
  app.run(
    host = '0.0.0.0',
    debug = True
  )
