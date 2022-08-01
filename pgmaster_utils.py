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

import git
import psycopg2.extensions

def git_ancestor(commit: git.Commit):
  """
  git_ancestor() - Search and get parents of specified commit
    commit : git.Commit instance to get parents' commits
  """
  def git_parents(p):
    result = []
    if p is None:
      return result

    if len(p.parents) > 1:
      # Merge commit
      for gp in p.parents:
        result.extend(git_parents(gp))
    else:
      # Initial or Normal commit
      result.extend([p.hexsha])

    return result
  # end of nested (internal) function

  if len(commit.parents) > 1:
    # Start point is a merge commit. Not supported.
    raise ValueError
  if len(commit.parents) < 1:
    # Initial commit
    return None

  return git_parents(commit.parents[0])

def git_children(cur: psycopg2.extensions.cursor, project: str, commit: str):
  """
  git_children() - Search and get children of specified commit from database.
    cur     : psycopg2.extensions.cursor instance of databse
    project : project name
    commit  : Commit ID to get children's commits
  """
  cur.execute(u"""SELECT
      children
    FROM
      _commitinfo
    WHERE
      project = %s and
      commitid = %s""",
    [project, commit]
  )
  (children,) = cur.fetchone()
  if children is None:
    return None
  return children
