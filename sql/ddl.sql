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

--# uninstall each tables.
DROP TABLE IF EXISTS project_info;
DROP TABLE IF EXISTS repository_info;
DROP TABLE IF EXISTS _branch CASCADE;
DROP TABLE IF EXISTS _investige CASCADE;
DROP TABLE IF EXISTS _commitinfo CASCADE;

CREATE TABLE IF NOT EXISTS project_info
(
  project          text PRIMARY KEY,
  repo_browse_url  text
);

 CREATE TABLE IF NOT EXISTS repository_info
(
  project  text NOT NULL,
  branch   text NOT NULL,
  PRIMARY KEY(project, branch)
);

CREATE TABLE IF NOT EXISTS _branch
(
  project      text        NOT NULL,
  branch       text        NOT NULL,
  commitid     text        NOT NULL,
  scommitid    text        NOT NULL, -- (short)commitid (7+ letters)
  commitdate   timestamptz NOT NULL, -- commitdate with timezone
  commitdate_l timestamp   NOT NULL, -- commitdate by localtime
  timezone_int smallint    NOT NULL, -- timezone of commit
  updatetime   timestamptz NOT NULL default now(),
  PRIMARY KEY(project, commitid, branch)
)
PARTITION BY list ( project );

CREATE INDEX _branch_commitdate_brin ON _branch USING brin(commitdate);
CREATE INDEX _branch_commitid_hash ON _branch USING hash(commitid);

CREATE TABLE IF NOT EXISTS _commitinfo
(
  project      text        NOT NULL,
  commitid     text        NOT NULL,
  updatetime   timestamptz NOT NULL default now(),
  author       text        NOT NULL,
  committer    text        NOT NULL,
  commitlog    text        NOT NULL,
  children     text[],
  PRIMARY KEY(project, commitid)
)
PARTITION BY list ( project );

CREATE INDEX _commitinfo_commitlog_hash ON _commitinfo USING hash(commitlog);

CREATE TABLE IF NOT EXISTS _investigation
(
  project    text NOT NULL,
  branch     text NOT NULL,
  commitid   text NOT NULL,
  updatetime timestamptz NOT NULL default now(),
  snote      text,     -- Summary of this commit
  note       text,     -- Commit message of this commit
  analysis   text,     -- Analyzing memo of this commit
  keywords   text[],   -- Keywords of this commit
  PRIMARY KEY(project, commitid, branch)
)
PARTITION BY list ( project );

CREATE INDEX _investigation_commitid_hash ON _investigation USING hash(commitid);

