# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module to provide implicit behavior based on enviroment.

Acts as a mutable namespace to allow the datastore package to
imply the current dataset ID and connection from the enviroment.
"""

import os
import socket

from six.moves.http_client import HTTPConnection  # pylint: disable=F0401

try:
    from google.appengine.api import app_identity
except ImportError:
    app_identity = None


_DATASET_ENV_VAR_NAME = 'GCLOUD_DATASET_ID'
_GCD_DATASET_ENV_VAR_NAME = 'DATASTORE_DATASET'


def app_engine_id():
    """Gets the App Engine application ID if it can be inferred.

    :rtype: string or ``NoneType``
    :returns: App Engine application ID if running in App Engine,
              else ``None``.
    """
    if app_identity is None:
        return None

    return app_identity.get_application_id()


def compute_engine_id():
    """Gets the Compute Engine project ID if it can be inferred.

    Uses 169.254.169.254 for the metadata server to avoid request
    latency from DNS lookup.

    See https://cloud.google.com/compute/docs/metadata#metadataserver
    for information about this IP address. (This IP is also used for
    Amazon EC2 instances, so the metadata flavor is crucial.)

    See https://github.com/google/oauth2client/issues/93 for context about
    DNS latency.

    :rtype: string or ``NoneType``
    :returns: Compute Engine project ID if the metadata service is available,
              else ``None``.
    """
    host = '169.254.169.254'
    uri_path = '/computeMetadata/v1/project/project-id'
    headers = {'Metadata-Flavor': 'Google'}
    connection = HTTPConnection(host, timeout=0.1)

    try:
        connection.request('GET', uri_path, headers=headers)
        response = connection.getresponse()
        if response.status == 200:
            return response.read()
    except socket.error:  # socket.timeout or socket.error(64, 'Host is down')
        pass
    finally:
        connection.close()


def _determine_default_dataset_id(dataset_id=None):
    """Determine default dataset ID explicitly or implicitly as fall-back.

    In implicit case, supports four environments. In order of precedence, the
    implicit environments are:

    * GCLOUD_DATASET_ID environment variable
    * DATASTORE_DATASET environment variable (for ``gcd`` testing)
    * Google App Engine application ID
    * Google Compute Engine project ID (from metadata server)

    :type dataset_id: string
    :param dataset_id: Optional. The dataset ID to use as default.

    :rtype: string or ``NoneType``
    :returns: Default dataset ID if it can be determined.
    """
    if dataset_id is None:
        dataset_id = os.getenv(_DATASET_ENV_VAR_NAME)

    if dataset_id is None:
        dataset_id = os.getenv(_GCD_DATASET_ENV_VAR_NAME)

    if dataset_id is None:
        dataset_id = app_engine_id()

    if dataset_id is None:
        dataset_id = compute_engine_id()

    return dataset_id


def set_default_dataset_id(dataset_id=None):
    """Set default dataset ID either explicitly or implicitly as fall-back.

    In implicit case, supports four environments. In order of precedence, the
    implicit environments are:

    * GCLOUD_DATASET_ID environment variable
    * DATASTORE_DATASET environment variable (for ``gcd`` testing)
    * Google App Engine application ID
    * Google Compute Engine project ID (from metadata server)

    :type dataset_id: string
    :param dataset_id: Optional. The dataset ID to use as default.

    :raises: :class:`EnvironmentError` if no dataset ID was implied.
    """
    dataset_id = _determine_default_dataset_id(dataset_id=dataset_id)
    if dataset_id is not None:
        _DEFAULTS.dataset_id = dataset_id
    else:
        raise EnvironmentError('No dataset ID could be inferred.')


def get_default_dataset_id():
    """Get default dataset ID.

    :rtype: string or ``NoneType``
    :returns: The default dataset ID if one has been set.
    """
    return _DEFAULTS.dataset_id


def get_default_connection():
    """Get default connection.

    :rtype: :class:`gcloud.datastore.connection.Connection` or ``NoneType``
    :returns: The default connection if one has been set.
    """
    return _DEFAULTS.connection


class _LazyProperty(object):
    """Descriptor for lazy loaded property.

    This follows the reify pattern: lazy evaluation and then replacement
    after evaluation.

    :type name: string
    :param name: The name of the attribute / property being evaluated.

    :type deferred_callable: callable that takes no arguments
    :param deferred_callable: The function / method used to evaluate the
                              property.
    """

    def __init__(self, name, deferred_callable):
        self._name = name
        self._deferred_callable = deferred_callable

    def __get__(self, obj, objtype):
        if obj is None or objtype is not _DefaultsContainer:
            return self

        setattr(obj, self._name, self._deferred_callable())
        return getattr(obj, self._name)


def _lazy_property_deco(deferred_callable):
    """Decorator a method to create a :class:`_LazyProperty`.

    :type deferred_callable: callable that takes no arguments
    :param deferred_callable: The function / method used to evaluate the
                              property.

    :rtype: :class:`_LazyProperty`.
    :returns: A lazy property which defers the deferred_callable.
    """
    if isinstance(deferred_callable, staticmethod):
        # H/T: http://stackoverflow.com/a/9527450/1068170
        #      For Python2.7+ deferred_callable.__func__ would suffice.
        deferred_callable = deferred_callable.__get__(True)
    return _LazyProperty(deferred_callable.__name__, deferred_callable)


class _DefaultsContainer(object):
    """Container for defaults.

    :type connection: :class:`gcloud.datastore.connection.Connection`
    :param connection: Persistent implied connection from environment.

    :type dataset_id: string
    :param dataset_id: Persistent implied dataset ID from environment.
    """

    @_lazy_property_deco
    @staticmethod
    def dataset_id():
        """Return the implicit default dataset ID."""
        return _determine_default_dataset_id()

    def __init__(self, connection=None, dataset_id=None, implicit=False):
        self.connection = connection
        if dataset_id is not None or not implicit:
            self.dataset_id = dataset_id


_DEFAULTS = _DefaultsContainer(implicit=True)
