from __future__ import absolute_import, unicode_literals

from arango.api import APIWrapper, api_method
from arango.utils import HTTP_OK
from arango.cursor import Cursor
from arango.exceptions import (
    AQLQueryExplainError,
    AQLQueryValidateError,
    AQLQueryExecuteError,
    AQLFunctionCreateError,
    AQLFunctionDeleteError,
    AQLFunctionsListError,
    AQLCacheClearError,
    AQLCacheConfigureError,
    AQLCacheGetPropertiesError
)
from arango.request import Request


class AQL(APIWrapper):
    """Wrapper for invoking ArangoDB Query Language (AQL).

    :param connection: ArangoDB database connection
    :type connection: arango.connection.Connection
    """

    def __init__(self, connection):
        self._conn = connection
        self._cache = AQLQueryCache(self._conn)

    def __repr__(self):
        return "<ArangoDB AQL>"

    @property
    def cache(self):
        """Return the query cache object.

        :returns: the query cache
        :rtype: arango.query.AQLQueryCache
        """
        return self._cache

    @api_method
    def explain(self, query, all_plans=False, max_plans=None, opt_rules=None):
        """Inspect the query and return its metadata.

        :param query: the query to inspect
        :type query: str
        :param all_plans: if ``True`` all possible execution plans are
            returned, otherwise only the optimal one is returned
        :type all_plans: bool
        :param max_plans: the total number of plans generated by the optimizer
        :type max_plans: int
        :param opt_rules: the list of optimizer rules
        :type opt_rules: list
        :returns: the plan or plans if `all_plans` is set to ``True``
        :rtype: list | dict
        :raises arango.exceptions.AQLQueryExplainError: if the query cannot be
            explained
        """
        options = {'allPlans': all_plans}
        if max_plans is not None:
            options['maxNumberOfPlans'] = max_plans
        if opt_rules is not None:
            options['optimizer'] = {'rules': opt_rules}

        request = Request(
            method='post',
            endpoint='/_api/explain',
            data={'query': query, 'options': options}
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLQueryExplainError(res)
            return res.body['plan' if 'plan' in res.body else 'plans']

        return request, handler

    @api_method
    def validate(self, query):
        """Validate the query.

        :param query: the query to validate
        :type query: str
        :returns: whether the validation was successful
        :rtype: bool
        :raises arango.exceptions.AQLQueryValidateError: if the query cannot be
            validated
        """
        request = Request(
            method='post',
            endpoint='/_api/query',
            data={'query': query}
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLQueryValidateError(res)
            res.body.pop('code', None)
            res.body.pop('error', None)
            return res.body

        return request, handler

    @api_method
    def execute(self, query, count=False, batch_size=None, ttl=None,
                bind_vars=None, full_count=None, max_plans=None,
                optimizer_rules=None):
        """Execute the query and return the result cursor.

        :param query: the AQL query to execute
        :type query: str
        :param count: whether the document count should be returned
        :type count: bool
        :param batch_size: maximum number of documents in one round trip
        :type batch_size: int
        :param ttl: time-to-live for the cursor (in seconds)
        :type ttl: int
        :param bind_vars: key-value pairs of bind parameters
        :type bind_vars: dict
        :param full_count: include count before last LIMIT
        :param max_plans: maximum number of plans the optimizer generates
        :type max_plans: int
        :param optimizer_rules: list of optimizer rules
        :type optimizer_rules: list
        :returns: document cursor
        :rtype: arango.cursor.Cursor
        :raises arango.exceptions.AQLQueryExecuteError: if the query cannot be
            executed
        :raises arango.exceptions.CursorCloseError: if the cursor cannot be
            closed properly
        """
        options = {}
        if full_count is not None:
            options['fullCount'] = full_count
        if max_plans is not None:
            options['maxNumberOfPlans'] = max_plans
        if optimizer_rules is not None:
            options['optimizer'] = {'rules': optimizer_rules}

        data = {'query': query, 'count': count}
        if batch_size is not None:
            data['batchSize'] = batch_size
        if ttl is not None:
            data['ttl'] = ttl
        if bind_vars is not None:
            data['bindVars'] = bind_vars
        if options:
            data['options'] = options

        request = Request(
            method='post',
            endpoint='/_api/cursor',
            data=data
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLQueryExecuteError(res)
            return Cursor(self._conn, res.body)

        return request, handler

    @api_method
    def functions(self):
        """List the AQL functions defined in this database.

        :returns: a mapping of AQL function names to its javascript code
        :rtype: dict
        :raises arango.exceptions.AQLFunctionsListError: if the AQL functions
            cannot be retrieved
        """
        request = Request(method='get', endpoint='/_api/aqlfunction')

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLFunctionsListError(res)
            body = res.body or {}
            return {func['name']: func['code'] for func in map(dict, body)}

        return request, handler

    @api_method
    def create_function(self, name, code):
        """Create a new AQL function.

        :param name: the name of the new AQL function to create
        :type name: str
        :param code: the definition of the function in Javascript
        :type code: str
        :returns: whether the AQL function was created successfully
        :rtype: bool
        :raises arango.exceptions.AQLFunctionCreateError: if the AQL function
            cannot be created
        """
        request = Request(
            method='post',
            endpoint='/_api/aqlfunction',
            data={'name': name, 'code': code}
        )

        def handler(res):
            if res.status_code not in (200, 201):
                raise AQLFunctionCreateError(res)
            return not res.body['error']

        return request, handler

    @api_method
    def delete_function(self, name, group=None, ignore_missing=False):
        """Delete the AQL function of the given name.

        If ``group`` is set to True, then the function name provided in
        ``name`` is treated as a namespace prefix, and all functions in
        the specified namespace will be deleted. If set to False, the
        function name provided in ``name`` must be fully qualified,
        including any namespaces.

        :param name: the name of the AQL function to delete
        :type name: str
        :param group: treat the name as a namespace prefix
        :type group: bool
        :param ignore_missing: ignore missing functions
        :type ignore_missing: bool
        :returns: whether the AQL function was deleted successfully
        :rtype: bool
        :raises arango.exceptions.AQLFunctionDeleteError: if the AQL function
            cannot be deleted
        """
        request = Request(
            method='delete',
            endpoint='/_api/aqlfunction/{}'.format(name),
            params={'group': group} if group is not None else {}
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                if not (res.status_code == 404 and ignore_missing):
                    raise AQLFunctionDeleteError(res)
            return not res.body['error']

        return request, handler


class AQLQueryCache(APIWrapper):
    """ArangoDB query cache.

    :param connection: ArangoDB database connection
    :type connection: arango.connection.Connection
    """

    def __init__(self, connection):
        self._conn = connection

    @api_method
    def properties(self):
        """Return the properties of the query cache.

        :returns: the cache properties
        :rtype: dict
        :raises arango.exceptions.AQLCacheGetPropertiesError: if the cache
            properties cannot be retrieved
        """
        request = Request(
            method='get',
            endpoint='/_api/query-cache/properties'
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLCacheGetPropertiesError(res)
            return {'mode': res.body['mode'], 'limit': res.body['maxResults']}

        return request, handler

    @api_method
    def configure(self, mode=None, limit=None):
        """Configure the AQL query cache.

        :param mode: the operation mode (``"off"``, ``"on"`` or ``"demand"``)
        :type mode: str
        :param limit: the maximum number of results to be stored
        :type limit: int
        :returns: the result of the operation
        :rtype: dict
        :raises arango.exceptions.AQLCacheConfigureError: if the
            cache properties cannot be updated
        """
        data = {}
        if mode is not None:
            data['mode'] = mode
        if limit is not None:
            data['maxResults'] = limit

        request = Request(
            method='put',
            endpoint='/_api/query-cache/properties',
            data=data
        )

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLCacheConfigureError(res)
            return {'mode': res.body['mode'], 'limit': res.body['maxResults']}

        return request, handler

    @api_method
    def clear(self):
        """Clear any results in the query cache.

        :returns: the result of the operation
        :rtype: dict
        :raises arango.exceptions.AQLCacheClearError: if the cache query
            cannot be cleared
        """
        request = Request(method='delete', endpoint='/_api/query-cache')

        def handler(res):
            if res.status_code not in HTTP_OK:
                raise AQLCacheClearError(res)
            return not res.body['error']

        return request, handler