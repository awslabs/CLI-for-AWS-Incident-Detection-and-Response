from injector import Module, provider, singleton

from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.services.file_cache.file_cache_deserializer import (
    FileCacheDeserializer,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class FileCacheModule(Module):
    """File cache services module."""

    @singleton
    @provider
    def provide_file_cache_service(
        self, logger: CliLogger, deserializer: FileCacheDeserializer
    ) -> FileCacheServiceInterface:
        """
        Provide file cache service implementation.
        """
        return FileCacheService(logger=logger, deserializer=deserializer)
