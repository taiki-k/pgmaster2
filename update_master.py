#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020-2022 Kondo Taiki
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
import psycopg2
import datetime, time
import fcntl
import argparse
import configparser
import traceback
import concurrent.futures
from git import *

import pg_connection
import pgmaster_utils

pg_conn = None

def get_now(with_date = False):
  """
  get_now() - Get the current time
  with_date : True if you want to get current date and time
  """
  if with_date:
    return datetime.datetime.now().strftime(u'%Y-%m-%d %H:%M:%S')
  else:
    return datetime.datetime.now().strftime(u'%H:%M:%S')

def update_repo(param):
  """
  update_repo - Update repository information
  param : tuple of following
    project : project name
    num     : number of this worker
    force   : DO force importing
  """
  (project, num, force) = param

  fd = None
  conn = pg_conn.connect()
  print(u"LOG[%d] <%s>: Connect to database for %s" % (num, get_now(), project))

  try:
    fd = open(u'git/.lock.' + project, 'w')
    fcntl.flock(fd, fcntl.LOCK_EX)  # LOCK
    repo = Repo(u'git/' + project + u'.git')
    git_cmd = repo.git
    branches = []

    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
          branch
        FROM
          repository_info
        WHERE
          project = %s""",
        [project]
      )
      branches.extend([r for (r,) in cursor.fetchall()])
    
    print(u"LOG[%d] <%s>: Fetch from origin on %s" % (num, get_now(), project))
    repo.remotes.origin.fetch()
    print(u"LOG[%d] <%s>: Fetch done" % (num, get_now()))

    # Determine the start point to insert.
    for branch in branches:
      print(u"INFO[%d] <%s>: Start updating \"%s\"." % (num, get_now(), branch))
      since = None
      # When doing force importing, all commits are processed,
      # so no need to calculate start point in this situation.
      if not force:
        with conn.cursor() as cursor:
          # To avoid commit slipped out,
          # start point is set to 1 day before the last commit date.
          cursor.execute(u"""SELECT
              (max(commitdate) - interval '1 day')::date
            FROM
              _branch
            WHERE
              project = %s and branch = %s
            LIMIT 1""",
            [project, branch]
          )
          (since,) = cursor.fetchone()

      # GitPython does NOT support "--no-merges" option,
      # use "--max-parents=1" instead.
      records = None
      if since is not None:
        records = repo.iter_commits(
          branch, max_parents = 1, since=since.strftime(u'%Y-%m-%d')
        )
      else:
        records = repo.iter_commits(
          branch, max_parents = 1
        )
      
      # Insert to database
      # repo.iter_commits returns from latest to oldest,
      # so we have to reverse the record list.
      with conn.cursor() as cursor:
        for record in reversed(list(records)):
          commit_id = record.hexsha
          s_commit_id = git_cmd.rev_parse(commit_id, short=7)
          commit_date = u"%s+0" % time.strftime(
            u"%Y-%m-%d %H:%M:%S",
            time.gmtime(record.authored_date)
          )
          time_zone = (-record.author_tz_offset // 36)  # (-1) * offset_sec / 3600 * 100
          commit_date_local = time.strftime(
            u"%Y-%m-%d %H:%M:%S",
            time.gmtime(
              record.authored_date + ((time_zone // 100) * 3600) + (time_zone % 100) * 60
            )
          )

          try:
            dml_insert_branch = u"""INSERT INTO
                _branch (project, branch, commitid, scommitid, commitdate, commitdate_l, timezone_int)
              VALUES
                (%s, %s, %s, %s, %s, %s, %s)"""
            if force:
              # To simply skip when record is already existed, add "ON CONFLICT ... DO NOTHING" clause.
              dml_insert_branch += u' ON CONFLICT ON CONSTRAINT _branch_pkey DO NOTHING'

            cursor.execute(dml_insert_branch,
              [project, branch, commit_id, s_commit_id, commit_date, commit_date_local, time_zone]
            )

            # There is NO "branch" column on _commitinfo table,
            # because we want to avoid duplicate records of large text data like commit message.
            # This is why only this SQL has "ON CONFLICT ... DO NOTHING" clause.
            cursor.execute(u"""INSERT INTO
                _commitinfo (project, commitid, author, committer, commitlog)
              VALUES
                (%s, %s, %s, %s, %s)
              ON CONFLICT ON CONSTRAINT _commitinfo_pkey DO NOTHING""",
              [project, commit_id, record.author.name, record.committer.name, record.message]
            )

            # Record commit-ids of "child" here.
            parents = pgmaster_utils.git_ancestor(record)
            if parents is not None:
              for parent in parents:
                children_old = pgmaster_utils.git_children(cursor, project, parent)
                children = [commit_id]
                children.extend(children_old if children_old is not None else [])
                if set(children) != set(children_old if children_old is not None else []):
                  # Need to update
                  cursor.execute(u"""UPDATE
                      _commitinfo
                    SET
                      children = %s,
                      updatetime = now()
                    WHERE
                      project = %s and
                      commitid = %s""",
                    [list(set(children)), project, parent]
                  )
                  print(u"LOG[%d] <%s>: Commit '%s' updated for child '%s'." % (num, get_now(), parent, commit_id))
                else:
                  print(u"INFO[%d] <%s>: Commit '%s' is not needed to update. Skip" % (num, get_now(), parent))

            conn.commit()
            print(u"LOG[%d] <%s>: Commit '%s' inserted." % (num, get_now(), commit_id))
          except psycopg2.Error as e:
            conn.rollback()
            if e.pgcode == '23505':
              # Unique constraint violation on _branch (partitioned) table.
              # This is expected because trying to insert from 1 day BEFORE last inserted.
              # Therefore, simply ignoring.
              print(u"INFO[%d] <%s>: Commit '%s' already exists. Skip." % (num, get_now(), commit_id))
            else:
              print(u"ERROR[%d] <%s>: %s ERRORCODE: %s" % (num, get_now(), e.pgerror, e.pgcode))
              raise
          except Exception as e:
            conn.rollback()
            raise
        # end of for records
      # end of with
      print(u"INFO[%d] <%s>: done." % (num, get_now()))
    # end of for branches

    # Push to other remote repositories if defined.
    # Remote name must be other than "origin".
    for remote_repo in repo.remotes:
      if remote_repo.name == "origin":
        print(u"INFO[%d] <%s>: Mirroring to remote 'origin' is skipped." % (num, get_now()))
        continue

      try:
        git_cmd.push(remote_repo.name, u'--all')
        print(u"LOG[%d] <%s>: Pushed all branches to '%s'." % (num, get_now(), remote_repo.name))
        git_cmd.push(remote_repo.name, u'--tags')
        print(u"LOG[%d] <%s>: Pushed all tags to '%s'." % (num, get_now(), remote_repo.name))
      except Exception as e:
        print(u"ERROR[%d] <%s>: Error occurred while mirroring to '%s'. (%s)" % (num, get_now(), remote_repo.name, str(e)))
        print((u"DETAIL[%d]: " % (num)) + traceback.format_exc())
        # Don't stop mirroring.

  except Exception as e:
    print(u"ERROR[%d] <%s>: Error occurred. (%s)" % (num, get_now(), str(e)))
    print((u"DETAIL[%d]: " % (num)) + traceback.format_exc())
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK
      fd.close()
    pg_conn.close(conn)

def main(force: bool = False):
  """
  Main
  """

  if force:
    print("LOG[0] <%s>: Specified force importing." % get_now())

  conn = pg_conn.connect()
  rows = []
  try:
    print("LOG[0] <%s>: connect for getting project informations." % get_now())
    with conn.cursor() as cursor:
      cursor.execute(u"""SELECT
        project
      FROM
        project_info"""
      )
      rows.extend([r for (r,) in cursor.fetchall()])
  except Exception as e:
    print(u"ERROR[0] <%s>: Error occurred. (%s)" % (get_now(), str(e)))
    print(u"DETAIL[0]: " + traceback.format_exc())
    sys.exit(1)
  finally:
    pg_conn.close(conn)

  if len(rows) <= 0:
    pass
  elif len(rows) == 1:
    update_repo((rows[0], 1, force))
  else:
    with concurrent.futures.ProcessPoolExecutor(max_workers = len(rows)) as executor:
      params = map(lambda n : (rows[n], n + 1, force), range(0, len(rows)))
      executor.map(update_repo, params)

if __name__ == "__main__":
  print("LOG[0] <%s>: Start to update repository information from <%s>" % (get_now(),get_now(True)))

  # Parse arguments.
  arg_parser = argparse.ArgumentParser()
  arg_parser.add_argument("-f", "--force", action = 'store_true', help = u"Force import. (This may take a long time)")
  args = arg_parser.parse_args()

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
    pooling = 0 # Ignore setting
  )

  main(args.force)

  print("LOG[0] <%s>: All have done. <%s>" % (get_now(), get_now(True)))
