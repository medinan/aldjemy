import warnings
from collections import deque
from django.db import connections
from django.conf import settings
from sqlalchemy import MetaData, create_engine, orm
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy.pool import _ConnectionRecord as _ConnectionRecordBase

from .table import generate_tables
from .wrapper import Wrapper
from .sqlite import SqliteWrapper

import time


__all__ = ['get_engine', 'get_meta', 'get_tables']


class CacheType(type):

    def __getattribute__(cls, name):
        if name == 'models':
            warnings.warn('Cache.models attribute is deprecated. '
                          'Use Cache.sa_models instead.',
                          DeprecationWarning, stacklevel=2)
        return type.__getattribute__(cls, name)


class Cache(object):
    """Module level cache"""
    __metaclass__ = CacheType
    engines = {}


SQLALCHEMY_ENGINES = {
    'sqlite3': 'sqlite',
    'mysql': 'mysql',
    'postgresql': 'postgresql',
    'postgresql_psycopg2': 'postgresql+psycopg2',
    'oracle': 'oracle',
}
SQLALCHEMY_ENGINES.update(getattr(settings, 'ALDJEMY_ENGINES', {}))


def get_engine_string(alias):
    sett = connections[alias].settings_dict
    return sett['ENGINE'].rsplit('.')[-1]


def get_connection_string(alias='default'):
    engine = SQLALCHEMY_ENGINES[get_engine_string(alias)]
    options = '?charset=utf8' if engine == 'mysql' else ''
    return engine + '://' + options


def get_engine(alias='default'):
    if alias not in Cache.engines:
        engine_string = get_engine_string(alias)
        # we have to use autocommit=True, because SQLAlchemy
        # is not aware of Django transactions
        pool = DjangoPool(
            alias=alias,
            creator=None,
            echo=getattr(settings, 'SA_ECHO_POOL', False),
            pool_size=getattr(settings, 'SA_POOL_SIZE', 10),
            max_overflow=getattr(settings, 'SA_POOL_MAX_OVERFLOW', 10),
            pre_ping=getattr(settings, 'SA_POOL_PREPING', False),
            recycle=getattr(settings, 'SA_RECYCLE', -1),
        )
        kw = {
            'pool': pool,
            'echo': getattr(settings, 'SA_ECHO', False),
            'strategy':getattr(settings, 'SA_STRATEGY', 'threadlocal')
        }
        if engine_string == 'sqlite3':
            kw['native_datetime'] = True

        Cache.engines[alias] = create_engine(get_connection_string(alias), **kw)
    return Cache.engines[alias]


def get_meta():
    if not getattr(Cache, 'meta', None):
        Cache.meta = MetaData()
    return Cache.meta


def get_tables():
    if not getattr(Cache, 'tables_loaded', False):
        generate_tables(get_meta())
        Cache.tables_loaded = True
    return get_meta().tables


class DjangoPool(QueuePool):
    def __init__(self, alias, *args, **kwargs):
        super(DjangoPool, self).__init__(*args, **kwargs)
        self.alias = alias

    def status(self):
        return "DjangoQueuePool"

    def _create_connection(self):
        return _ConnectionRecord(self, self.alias)

    def recreate(self):
        self.logger.info("Pool recreating")

        return DjangoPool(
            self.alias,
            self._creator, pool_size=self._pool.maxsize,
            max_overflow=self._max_overflow,
            timeout=self._timeout,
            recycle=self._recycle, echo=self.echo,
            logging_name=self._orig_logging_name,
            use_threadlocal=self._use_threadlocal,
            reset_on_return=self._reset_on_return,
            _dispatch=self.dispatch,
            dialect=self._dialect
        )


class _ConnectionRecord(_ConnectionRecordBase):
    def __init__(self, pool, alias):
        self.__pool = pool
        self.info = {}
        self.finalize_callback = deque()
        self.starttime = time.time()

        self.alias = alias
        self.wrap = False
        #pool.dispatch.first_connect.exec_once(self.connection, self)
        pool.dispatch.connect(self.connection, self)
        self.wrap = True

    @property
    def connection(self):
        connection = connections[self.alias]
        if connection.connection is None:
            connection._cursor()
        if connection.vendor == 'sqlite':
            return SqliteWrapper(connection.connection)
        if self.wrap:
            return Wrapper(connection.connection)
        return connection.connection

    def close(self):
        pass

    def invalidate(self, e=None, soft=False):
        pass

    def get_connection(self):
        return self.connection
