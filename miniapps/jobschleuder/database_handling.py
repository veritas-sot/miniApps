import psycopg2
import psycopg2.extras

def update_operating_database(cursor, device, running, startup):
    result = running and startup

    if result:
        message = f'successfully backed up running and startup config for {device}'
        sql = """INSERT INTO device_backups (device, last_attempt, last_success, status, retries, message) VALUES(%s, now(), now(), TRUE, 0, %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, last_success, status, retries, message) = (now(), now(), TRUE, 0, EXCLUDED.message)"""
        cursor.execute(sql, (device, message))
    else:
        message = f'failed to backup running and/or startup config for {device} - {running} - {startup}'
        sql = """INSERT INTO device_backups (device, last_attempt, status, retries, message) VALUES(%s, now(), FALSE, 0, %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, status, retries, message) = (now(), FALSE, EXCLUDED.retries + 1, EXCLUDED.message)"""
        cursor.execute(sql, (device, message))

    # commit data
    cursor.connection.commit()

def connect_to_db(database):
    
    conn = psycopg2.connect(
        host=database['host'],
        database=database.get('database', 'operating'),
        user=database['user'],
        password=database['password'],
        port=database.get('port', 5432)
    )

    cursor = conn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)
    return conn, cursor

def close_database(cursor):
    cursor.close()
