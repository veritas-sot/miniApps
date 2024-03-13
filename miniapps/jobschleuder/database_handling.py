import psycopg2
import psycopg2.extras

def update_operating_database(cursor, device, running, startup):
    result = running and startup

    if result:
        message = f'successfully backed up running and startup config for {device}'
        sql = """INSERT INTO device_backups (device, last_attempt, last_success, message) VALUES(%s, now(), now(), %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, last_success, message) = (now(), now(), EXCLUDED.message)"""
        cursor.execute(sql, (device, message))
    else:
        message = f'failed to backup running and/or startup config for {device} - {running} - {startup}'
        sql = """INSERT INTO device_backups (device, last_attempt, message) VALUES(%s, now(), %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, message) = (now(), EXCLUDED.message)"""
        cursor.execute(sql, (device, message))

    # commit data
    cursor.connection.commit()
    cursor.close()

def connect_to_db(database):
    
    conn = psycopg2.connect(
        host=database['host'],
        database=database.get('database', 'operating'),
        user=database['user'],
        password=database['password'],
        port=database.get('port', 5432)
    )

    cursor = conn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)
    return cursor
