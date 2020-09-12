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

import psycopg2
import psycopg2.pool

class pg_connection:
  def __init__(self, server = '127.0.0.1', port = '5432', database = 'postgres', user = '', password = '', pooling = 0):
    """
    pg_connection() - Initialize the connection
    server   : Host name or IP address of the database server
    port     : Port number of the database server
    database : Database name for connecting
    user     : Username of the database
    password : Password for specified user
    pooling  : Maximum number of connection pooling (0 (No pooling) or 2+)
    """
    if pooling < 0 or pooling == 1:
      raise ValueError

    self._connect_info = {
      'server'   : server,
      'port'     : port,
      'database' : database,
      'user'     : user,
      'password' : password,
      'pooling'  : pooling
    }
    self._conn_pool = None
    return

  def connect(self):
    """
    Connect to the database.
    """
    dsn = (
      u"postgresql://%s:%s@%s:%s/%s" % (
        self._connect_info['user'],
        self._connect_info['password'],
        self._connect_info['server'],
        self._connect_info['port'],
        self._connect_info['database']
      )
    )
    if self._connect_info['pooling'] > 0:
      if self._conn_pool is None:
        self._conn_pool = psycopg2.pool.ThreadedConnectionPool(
          2,
          self._connect_info['pooling'],
          dsn
        )
      conn = self._conn_pool.getconn()
      conn.autocommit = False
      return conn
    else:
      return psycopg2.connect(dsn)

  def close(self, conn):
    """
    Close the connection
    """
    if conn is None:
      raise ValueError

    if self._connect_info['pooling'] > 0:
      self._conn_pool.putconn(conn)
    else:
      conn.close()

  def closeall(self) :
    if self._connect_info['pooling'] <= 1:
      raise ValueError

    if self._conn_pool is None:
      return

    self._conn_pool.closeall()
    self._conn_pool = None
    return

  def __del__(self):
    try:
      self.closeall()
    except Exception:
      pass
