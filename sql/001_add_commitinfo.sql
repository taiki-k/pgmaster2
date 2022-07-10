/*
  Copyright (C) 2020-2022 Kondo Taiki

  This file is part of "pgmaster2".

  "pgmaster2" is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  "pgmaster2" is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with "pgmaster2".  If not, see <http://www.gnu.org/licenses/>.
*/

/*
  This is the migration script from database schema before commit "e6d9ea62".
  DO NOT APPLY after commit "cf9e4371".

  This script adds a new partitioned table named "_commitinfo",
  you MUST create child table for each projects,
  and run "update_python.py" with -f switch after creating tables.
*/

CREATE TABLE IF NOT EXISTS project_info
(
  project          text PRIMARY KEY,
  repo_browse_url  text
);

INSERT INTO project_info
  SELECT DISTINCT project, NULL FROM branch_info;

ALTER TABLE branch_info RENAME TO repository_info;
ALTER INDEX branch_info_pkey RENAME TO repository_info_pkey;

CREATE TABLE IF NOT EXISTS _commitinfo
(
  project      text        NOT NULL,
  commitid     text        NOT NULL,
  updatetime   timestamptz NOT NULL default now(),
  author       text        NOT NULL,
  committer    text        NOT NULL,
  commitlog    text        NOT NULL,
  PRIMARY KEY(project, commitid)
)
PARTITION BY list ( project );

CREATE INDEX _commitinfo_commitlog_hash ON _commitinfo USING hash(commitlog);
