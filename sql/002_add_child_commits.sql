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
  This is the migration script from database schema before commit "601c9de0".
  DO NOT APPLY after the next commit of "601c9de0".

  Run "update_python.py" with -f switch after running this script.
*/

ALTER TABLE _commitinfo ADD COLUMN children text[];
