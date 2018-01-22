import optparse
import os
import sys

from flask import Flask
from werkzeug.exceptions import NotFound
from werkzeug.serving import run_simple

from .exceptions import InvalidRequestException
from .models import database
from .models import Attachment
from .models import BlobData
from .models import Document
from .models import Index
from .models import IndexDocument
from .models import Metadata
from .views import register_views


def create_server(config=None, config_file=None):
    app = Flask(__name__)

    # Configure application using a config file.
    if config_file is not None:
        app.config.from_pyfile(config_file)

    # (Re-)Configure application using command-line switches/environment flags.
    if config is not None:
        app.config.from_object(config)

    # Initialize the SQLite database.
    initialize_database(app.config.get('DATABASE') or 'scout.db',
                        pragmas=app.config.get('SQLITE_PRAGMAS') or None)
    register_views(app)

    @app.errorhandler(InvalidRequestException)
    def handle_invalid_request(exc):
        return exc.response()

    @app.before_request
    def connect_database():
        if database.database != ':memory:':
            database.connect()

    @app.teardown_request
    def close_database(exc):
        if database.database != ':memory:' and not database.is_closed():
            database.close()

    return app


def initialize_database(database_file, pragmas=None):
    database.init(database_file, pragmas=pragmas)
    try:
        meth = database.execution_context
    except AttributeError:
        meth = database

    with meth:
        database.create_tables([
            Attachment,
            BlobData,
            Document,
            Index,
            IndexDocument,
            Metadata])


def main(app):
    if app.config['DEBUG']:
        app.run(host=app.config['HOST'], port=app.config['PORT'], debug=True)
    else:
        run_simple(
            hostname=app.config['HOST'],
            port=app.config['PORT'],
            application=app,
            threaded=True)


def panic(s, exit_code=1):
    sys.stderr.write('\033[91m%s\033[0m\n' % s)
    sys.stderr.flush()
    sys.exit(exit_code)


def get_option_parser():
    parser = optparse.OptionParser()
    parser.add_option(
        '-H',
        '--host',
        dest='host',
        help='The hostname to listen on. Defaults to 127.0.0.1.')
    parser.add_option(
        '-p',
        '--port',
        dest='port',
        help='The port to listen on. Defaults to 8000.',
        type='int')
    parser.add_option(
        '-s',
        '--stem',
        dest='stem',
        help='Specify stemming algorithm for content.')
    parser.add_option(
        '-d',
        '--debug',
        action='store_true',
        dest='debug',
        help='Run Flask app in debug mode.')
    parser.add_option(
        '-c',
        '--config',
        dest='config',
        help='Configuration module (python file).')
    parser.add_option(
        '--paginate-by',
        default=50,
        dest='paginate_by',
        help='Number of documents displayed per page of results, default=50',
        type='int')
    parser.add_option(
        '-k',
        '--api-key',
        dest='api_key',
        help='Set the API key required to access Scout.')
    parser.add_option(
        '-a',
        '--star-all',
        action='store_true',
        dest='star_all',
        help='Search query "*" returns all records')
    parser.add_option(
        '-C',
        '--cache-size',
        default=64,
        dest='cache_size',
        help='SQLite page-cache size (MB). Defaults to 64MB.',
        type='int')
    parser.add_option(
        '-f',
        '--fsync',
        action='store_true',
        dest='fsync',
        help='Synchronize database to disk on every write.')
    parser.add_option(
        '-j',
        '--journal-mode',
        default='wal',
        dest='journal_mode',
        help='SQLite journal mode. Defaults to WAL (recommended).')
    return parser

def parse_options():
    option_parser = get_option_parser()
    options, args = option_parser.parse_args()

    config_file = os.environ.get('SCOUT_CONFIG') or options.config
    config = {'DATABASE': os.environ.get('SCOUT_DATABASE')}

    if len(args) == 0 and not config['DATABASE']:
        panic('Error: missing required path to database file.')
    elif len(args) > 1:
        panic('Error: [%s] only accepts one argument, which is the path '
              'to the database file.' % __file__)
    elif args:
        config['DATABASE'] = args[0]

    pragmas = [('journal_mode', options.journal_mode)]
    if options.cache_size:
        pragmas.append(('cache_size', -1024 * options.cache_size))
    if not options.fsync:
        pragmas.append(('synchronous', 0))

    config['SQLITE_PRAGMAS'] = pragmas

    # Handle command-line options. These values will override any values
    # that may have been specified in the config file.
    if options.api_key:
        config['AUTHENTICATION'] = options.api_key
    if options.debug:
        config['DEBUG'] = True
    if options.host:
        config['HOST'] = options.host
    if options.port:
        config['PORT'] = options.port
    if options.paginate_by:
        if options.paginate_by < 1 or options.paginate_by > 1000:
            panic('paginate-by must be between 1 and 1000')
        config['PAGINATE_BY'] = options.paginate_by
    if options.star_all:
        config['STAR_ALL'] = True
    if options.stem:
        if options.stem not in ('simple', 'porter'):
            panic('Unrecognized stemmer. Must be "porter" or "simple".')
        config['STEM'] = options.stem

    return create_server(config, config_file)


if __name__ == '__main__':
    app = parse_options()
    main(app)
