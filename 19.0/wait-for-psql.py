#!/usr/bin/env python3
import argparse
import psycopg2
import sys
import time


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--db_host', required=True)
    arg_parser.add_argument('--db_port', required=True)
    arg_parser.add_argument('--db_user', required=True)
    arg_parser.add_argument('--db_password', required=True)
    arg_parser.add_argument('--db_name', default='postgres')
    arg_parser.add_argument('--db_sslmode', default=None)
    arg_parser.add_argument('--timeout', type=int, default=5)

    args = arg_parser.parse_args()

    start_time = time.time()
    while (time.time() - start_time) < args.timeout:
        try:
            conn_params = {
                'user': args.db_user,
                'host': args.db_host,
                'port': args.db_port,
                'password': args.db_password,
                'dbname': args.db_name,
            }
            if args.db_sslmode:
                conn_params['sslmode'] = args.db_sslmode
            conn = psycopg2.connect(**conn_params)
            error = ''
            break
        except psycopg2.OperationalError as e:
            error = e
        else:
            conn.close()
        time.sleep(1)

    if error:
        print("Database connection failure: %s" % error, file=sys.stderr)
        sys.exit(1)
