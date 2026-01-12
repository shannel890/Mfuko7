"""
Database Utilities for Read/Write Query Separation

Provides:
- Read-only session management
- Query optimization utilities
- Connection pooling strategy
- Future support for read replicas
- Query result caching

Improves:
- Dashboard query performance
- Report generation speed
- Database load distribution
- Scalability for growth
"""

from flask import current_app
from app.extensions import db
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool
import logging
from functools import wraps
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


class ReadOnlySession(Session):
    """
    Read-only SQLAlchemy session that prevents write operations.
    
    Used for dashboards and reports to ensure no accidental writes
    and to enable future connection to read replicas.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_read_only = True
    
    def add(self, instance):
        """Override add to prevent inserts in read-only mode."""
        if self._is_read_only:
            raise RuntimeError(
                "Cannot insert data in read-only session. "
                "Use the main session for write operations."
            )
        return super().add(instance)
    
    def delete(self, instance):
        """Override delete to prevent deletes in read-only mode."""
        if self._is_read_only:
            raise RuntimeError(
                "Cannot delete data in read-only session. "
                "Use the main session for write operations."
            )
        return super().delete(instance)
    
    def merge(self, instance, load=True):
        """Override merge to prevent updates in read-only mode."""
        if self._is_read_only:
            raise RuntimeError(
                "Cannot update data in read-only session. "
                "Use the main session for write operations."
            )
        return super().merge(instance, load=load)


class DatabaseManager:
    """
    Manages database connections with read/write separation.
    
    Features:
    - Separate read and write connections
    - Connection pooling
    - Query result caching
    - Future read replica support
    """
    
    def __init__(self, app=None):
        self.app = app
        self.read_session_factory = None
        self.write_session_factory = None
        self._query_cache = {}
        self._engine = None
        
        if app:
            self.init_app(app)
    
    @property
    def engine(self):
        """Lazy-load database engine within app context."""
        if self._engine is None:
            self._engine = db.engine
        return self._engine
    
    def init_app(self, app):
        """Initialize database manager with Flask app."""
        self.app = app
        
        # Create session factories without binding (will bind at runtime)
        # This avoids app context issues during initialization
        self.read_session_factory = sessionmaker(
            class_=ReadOnlySession,
            expire_on_commit=False
        )
        
        # Write session uses default Session
        self.write_session_factory = sessionmaker(
            expire_on_commit=False
        )
        
        logger.info("Database manager initialized with read/write separation")
    
    def get_read_session(self):
        """
        Get a read-only session.
        
        Used for:
        - Dashboard queries
        - Report generation
        - Analytics queries
        - Read-only views
        
        Returns:
            ReadOnlySession: A read-only database session
        """
        if not self.read_session_factory:
            raise RuntimeError("Database manager not initialized")
        
        # Bind to engine at runtime (within app context)
        session = self.read_session_factory(bind=self.engine)
        return session
    
    def get_write_session(self):
        """
        Get a write-enabled session.
        
        Used for:
        - Creating records
        - Updating records
        - Deleting records
        - All write operations
        
        Returns:
            Session: A writeable database session
        """
        if not self.write_session_factory:
            raise RuntimeError("Database manager not initialized")
        
        # Bind to engine at runtime (within app context)
        session = self.write_session_factory(bind=self.engine)
        return session
    
    def close_read_session(self, session):
        """Close a read session gracefully."""
        if session:
            session.close()
    
    def close_write_session(self, session):
        """Close a write session gracefully."""
        if session:
            session.close()


class QueryCache:
    """
    Simple in-memory query cache for read-heavy operations.
    
    Features:
    - Automatic cache key generation
    - TTL-based expiration
    - Cache invalidation
    - Hit/miss statistics
    
    Future:
    - Redis backend
    - Distributed cache
    - Cache warming
    """
    
    def __init__(self, ttl_seconds=300):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._cache = {}
        self._timestamps = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _generate_key(self, query_str, *args, **kwargs):
        """Generate cache key from query and parameters."""
        key_str = f"{query_str}:{str(args)}:{str(kwargs)}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key):
        """
        Get value from cache if it exists and hasn't expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._cache:
            self.misses += 1
            return None
        
        # Check if expired
        timestamp = self._timestamps.get(key)
        if timestamp and datetime.now() - timestamp > timedelta(seconds=self.ttl):
            del self._cache[key]
            del self._timestamps[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return self._cache[key]
    
    def set(self, key, value):
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = value
        self._timestamps[key] = datetime.now()
    
    def invalidate(self, pattern=None):
        """
        Invalidate cache entries.
        
        Args:
            pattern: If None, clear all. Otherwise clear matching keys
        """
        if pattern is None:
            self._cache.clear()
            self._timestamps.clear()
        else:
            keys_to_delete = [k for k in self._cache if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
                del self._timestamps[key]
    
    def get_stats(self):
        """Get cache hit/miss statistics."""
        total = self.hits + self.misses
        rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            'hits': self.hits,
            'misses': self.misses,
            'total_requests': total,
            'hit_rate': round(rate, 2),
            'cached_items': len(self._cache)
        }


class QueryOptimizer:
    """
    Utilities for optimizing database queries.
    
    Features:
    - Eager loading recommendations
    - Query analysis
    - Index suggestions
    - Batch operation utilities
    """
    
    @staticmethod
    def with_eager_load(query, *relationships):
        """
        Add eager loading to query.
        
        Args:
            query: SQLAlchemy query
            *relationships: Relationship names to eagerly load
            
        Returns:
            Query with eager loading applied
            
        Example:
            query = Payment.query
            query = QueryOptimizer.with_eager_load(query, 'tenant', 'invoice')
        """
        for relationship in relationships:
            query = query.outerjoin(relationship).options(
                db.joinedload(relationship)
            )
        return query
    
    @staticmethod
    def batch_query(model, ids, chunk_size=1000):
        """
        Query large number of IDs in batches.
        
        Prevents query size overflow and improves performance.
        
        Args:
            model: SQLAlchemy model class
            ids: List of IDs to query
            chunk_size: Number of IDs per batch
            
        Yields:
            Model instances
            
        Example:
            for tenant in QueryOptimizer.batch_query(Tenant, tenant_ids):
                process(tenant)
        """
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            for item in model.query.filter(model.id.in_(chunk)).all():
                yield item
    
    @staticmethod
    def count_with_limit(query, limit=10000):
        """
        Count query results with limit to prevent long-running queries.
        
        Args:
            query: SQLAlchemy query
            limit: Maximum count to return
            
        Returns:
            Count (capped at limit)
        """
        count = query.limit(limit + 1).count()
        return min(count, limit)
    
    @staticmethod
    def only_fields(query, model, *fields):
        """
        Select only specific fields from model.
        
        Reduces data transfer and improves performance.
        
        Args:
            query: SQLAlchemy query
            model: Model class
            *fields: Field names to select
            
        Returns:
            Query returning tuples with selected fields
            
        Example:
            payments = QueryOptimizer.only_fields(
                Payment.query, Payment,
                'id', 'amount', 'payment_date'
            )
        """
        columns = [getattr(model, field) for field in fields if hasattr(model, field)]
        return query.with_entities(*columns)
    
    @staticmethod
    def analyze_query_plan(query):
        """
        Analyze query execution plan (SQLite/PostgreSQL).
        
        Args:
            query: SQLAlchemy query
            
        Returns:
            Query plan details
        """
        try:
            # Convert SQLAlchemy query to string
            query_str = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
            
            # For PostgreSQL
            if 'postgresql' in str(db.engine.url):
                result = db.session.execute(f'EXPLAIN {query_str}')
                return [row for row in result]
            
            # For SQLite
            if 'sqlite' in str(db.engine.url):
                result = db.session.execute(f'EXPLAIN QUERY PLAN {query_str}')
                return [row for row in result]
            
            return None
        
        except Exception as e:
            logger.warning(f"Could not analyze query plan: {str(e)}")
            return None


def read_only(f):
    """
    Decorator for read-only database operations.
    
    Ensures operation uses read-only session.
    Useful for dashboards and reports.
    
    Example:
        @read_only
        def get_payment_stats():
            # Uses read-only session automatically
            return Payment.query.count()
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get database manager from app
        db_manager = current_app.extensions.get('db_manager')
        
        if not db_manager:
            # Fall back to regular session if manager not available
            return f(*args, **kwargs)
        
        # Use read-only session
        read_session = db_manager.get_read_session()
        try:
            # Inject read session into kwargs if not present
            if 'session' not in kwargs:
                kwargs['session'] = read_session
            
            return f(*args, **kwargs)
        
        finally:
            db_manager.close_read_session(read_session)
    
    return decorated_function


def write_only(f):
    """
    Decorator for write database operations.
    
    Ensures operation uses write-enabled session.
    Used for creates, updates, deletes.
    
    Example:
        @write_only
        def create_payment(tenant_id, amount):
            # Uses write-enabled session
            payment = Payment(tenant_id=tenant_id, amount=amount)
            db.session.add(payment)
            db.session.commit()
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db_manager = current_app.extensions.get('db_manager')
        
        if not db_manager:
            return f(*args, **kwargs)
        
        write_session = db_manager.get_write_session()
        try:
            if 'session' not in kwargs:
                kwargs['session'] = write_session
            
            return f(*args, **kwargs)
        
        finally:
            db_manager.close_write_session(write_session)
    
    return decorated_function


# Global instances
query_cache = QueryCache(ttl_seconds=300)  # 5-minute cache
optimizer = QueryOptimizer()


def get_database_manager():
    """Get the database manager instance."""
    try:
        return current_app.extensions.get('db_manager')
    except RuntimeError:
        return None
