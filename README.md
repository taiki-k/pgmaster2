# pgmaster2

Platform for investigation of each commits in git repositories, especially PostgreSQL.

## Copyright and License

Copyright (C) 2020-2023 Kondo Taiki

This software is licensed under the GPL v3.  
See `COPYING` file for more information.

If you don't recieve it, see [the GNU web site](http://www.gnu.org/licenses/).

## How to Setup

You can use "pgmaster2" as a standalone server,  
but you should use with Web server like Apache, nginx, lighttpd, via WSGI interface.

### Install required Python packages

You can use requirements.txt, so simply run following.

```
$ pip install -r requirements.txt
```

### Prepare Database

This depends on functionallity of PostgreSQL 11+,  
then you have to use PostgreSQL 11+ database.

#### Create Database

First, you have to create a new database like following.

```
$ createdb pgmaster
```
```
=# CREATE DATABASE pgmaster;
```

"pgmaster2" will do following operation to this database,  
you MUST grant database user "pgmaster2" uses to following operation.

* CONNECT
* LOGIN
* SELECT
* INSERT
* UPDATE
* CREATE TABLE

NOTE: "pgmaster2" does NOT use `CREATE TABLE` in this time, but will use in the future update.

#### Create Tables

The DDL is prepared in "sql/ddl.sql".  
Simply run with following command.

```
$ psql -a -f sql/ddl.sql [DATABASE]
```

### Create (or modify) Configuration (pgmaster.ini)

Create (or modify) `pgmaster.ini` file like following.

This file must have `PGMASTER` section, and this section must specify connection settings to PostgreSQL.

All entries are required, and will be passed to Psycopg2 module.

| Key      | Setting description                              |
| -------- | ------------------------------------------------ |
| Server   | Hostname or IP address of PostgreSQL to connect. |
| Port     | Port number of PostgreSQL to connect.            |
| Database | Database name of PostgreSQL to connect.          |
| User     | User of PostgreSQL to connect.                   |
| Password | RAW (un-encrypted) password for specified user.  |
| Pooling  | Number of pooling connections.                   |

If `trust` authentication is enabled on PostgreSQL to connect, value of `Password` entry is actually unused.  
But this entry is also required in this case, then you have to specify any strings to it.  

The sample of `pgmaster.ini` is following.

```ini
[PGMASTER]
Server = localhost
Port = 5432
Database = pgmaster
User = postgres
Password = dummy
Pooling = 5
```

### Standalone Server (Not recommended)

Simply run with following command.

```
$ python3 pgmaster.py
```

This is for development use only.  
We strictly recommend to use with WSGI compliant server (mentioned below) 
for production deployment.

### WSGI (Highly recommended)

This is build on Flask framework, so it will work with some WSGI compliant server.  
We tested with uWSGI, but it may work with any other WSGI compliant server.

For example, run uWSGI like following.

```
$ uwsgi --http=0.0.0.0:80 --enable-threads --wsgi-file=pgmaster.py --callable=app
```

When use with other than uWSGI, see documents of WSGI compliant server software you want to use.

## Manage repositories

### Create repository information for investigation

In this time, it is no features (but planning) to prepare any repositories to investigate.  
You have to run following steps manually.

#### Prepare git repository form remote

"pgmaster2" supports only mirror repository.  
So you must specify `--mirror` option to git command.

```
$ mkdir git
$ cd git
$ git clone --mirror http://example.com/some/where.git
```

Then, you will see `where.git` directory in current directory `git`.  
In following steps, we assume that project (repository) name is `where` (note: must ommit `.git`).

#### Prepare tables

Connect to database for using this purpose.

```
$ psql [DATABASE]
```

Create partitiond (child) table as following.  
This is a sample to manage *where* project cloned above.

```sql
=> CREATE TABLE IF NOT EXISTS "_branch_where" PARTITION OF _branch FOR VALUES IN ('where') PARTITION BY list ( branch );

=> CREATE TABLE IF NOT EXISTS "_invest_where" PARTITION OF _investigation FOR VALUES IN ('where') PARTITION BY list ( branch );

=> CREATE TABLE IF NOT EXISTS "_commitinfo_where" PARTITION OF _commitifo FOR VALUES IN ('where');
```

Create partitiond (grand-child) table as following.  
This is a sample to manage *main* branch in *where* project cloned above.

```sql
=> CREATE TABLE IF NOT EXISTS "branch_where_main" PARTITION OF _branch_where FOR VALUES IN ('main');

=> CREATE TABLE IF NOT EXISTS "invest_where_main" PARTITION OF _invest_where FOR VALUES IN ('main');
```

In this time, "pgmaster2" will manage data through "ROOT" tables  
(e.g. `_branch`, `_investigation`, and `_commitinfo`) of partition,  
therefore you can use any names for child and grand-child tables.

But, you **must note** that we plan to name these management tables  
**with following rules** when we implement create and delete features for them.

```
_branch
|
+- _branch_<project name>
   |
   +- branch_<project name>_<branch name>

_investigation
|
+- _invest_<project name>
   |
   +- invest_<project name>_<branch name>

_commitinfo
|
+- commitinfo_<project name>
```

#### Insert project & branch information

You have to insert project and branch information to investigate.  
This is a sample to manage *main* branch of *where* project cloned above.

```sql
=> INSERT INTO project_info (project) VALUES ('where');
=> INSERT INTO repository_info VALUES ('where', 'main');
```

#### Insert commit information

Same as update procedure mentioned below.

### Update commit information of managed repositories

Simply run with following command.

```
$ python3 update_master.py
```

`update_master.py` will insert new commits to your database.  
Running with cron is recommended.
