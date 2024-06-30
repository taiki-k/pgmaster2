# -*- coding: utf-8 -*-

# Copyright (C) 2020-2024 Kondo Taiki
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

import traceback
import psycopg2
import fcntl
from git import *
from flask import *

api = Blueprint('webapi_v1', __name__)

@api.route('/p/<project>/keyword')
def keywords(project):
  pg_conn = current_app.config['PG_CONNECTION']
  conn = pg_conn.connect()
  # Get keywords
  # TODO: Commonalize logic between here and normal page.
  keywords = []
  try:
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
  finally:
    pg_conn.close(conn)

  return jsonify({
    'succeed' : True,
    'keywords': keywords
  })

@api.route('/p/<project>/b/<path:branch>/c/<commitid>/modify', methods = ['POST'])
def investigate_modify(project, branch, commitid):
  """
  investigate_modify() - Insert or Update a result of investigation.
    project : project name
    branch  : branch name
    commitid: commitid
  """
  form_data = {}
  form_data.update(request.json)  # Make copy
  try:
    if len(form_data['snote']) <= 0:
      raise ValueError
    else:
      # Remove all of CR and LF.
      form_data['snote'] = u''.join(form_data['snote'].splitlines())

    if len(form_data['note']) <= 0:
      raise ValueError
    else:
      form_data['note'] = u'\n'.join(form_data['note'].splitlines())

    if len(form_data['analysis']) <= 0:
      pass
    else:
      form_data['analysis'] = u'\n'.join(form_data['analysis'].splitlines())
    
    if len(form_data['keywords']) <= 0:
      # We do NOT accept empty array, but should NOT be error.
      form_data['keywords'] = None
    else:
      pass

  except Exception as e:
    return jsonify({
      'succeed' : False,
      'trace' : traceback.format_exc()
    }), 403

  pg_conn = current_app.config['PG_CONNECTION']
  conn = pg_conn.connect()

  try:
    with conn.cursor() as cursor:
      cursor.execute(u"""INSERT INTO _investigation (
          project,
          branch,
          commitid,
          snote,
          note,
          analysis,
          keywords
        ) VALUES (
          %s,
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
          keywords = %s,
          updatetime = now()""",
        [
          project,
          branch,
          commitid,
          form_data['snote'],
          form_data['note'],
          form_data['analysis'],
          form_data['keywords'],
          form_data['snote'],  # for UPSERT
          form_data['note'],
          form_data['analysis'],
          form_data['keywords']
        ]
      )
    conn.commit()
  except psycopg2.Error as e:
    return jsonify({
      'succeed' : False,
      'trace' : traceback.format_exc()
    }), 500
  finally:
    pg_conn.close(conn)

  return jsonify({
    'succeed' : True
  })

@api.route('/p/<project>/c/<commitid>/translate', methods = ['GET'])
def translate_commitlog(project, commitid):
  try:
    from argostranslate.translate import translate
  except:
    return jsonify({
      'succeed' : False,
      'cause'   : u'Not supported on this instance.'
    }), 406

  # TODO : Read Accept-Language from browser
  translate_from = 'en'
  translate_to = 'ja'

  try:
    # Connect to git repository
    fd = open(u'git/.lock.' + project, 'r')
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)  # LOCK!
    repo = Repo(u'git/' + project + u'.git')

    if not repo.bare:
      raise FileNotFoundError

    # Translate here
    commit = repo.commit(commitid)
    translated_message = translate(commit.message, translate_from, translate_to)

  except (FileNotFoundError, ValueError) as e:
    return jsonify({
      'succeed' : False,
      'cause'   : u'Not Found.'
    }), 404
  except:
    return jsonify({
      'succeed' : False,
      'trace'   : traceback.format_exc()
    }), 500
  finally:
    if fd is not None:
      fcntl.flock(fd, fcntl.LOCK_UN)  # UNLOCK!
      fd.close()
      fd = None

  return jsonify({
    'succeed' : True,
    'message' : translated_message
  })
