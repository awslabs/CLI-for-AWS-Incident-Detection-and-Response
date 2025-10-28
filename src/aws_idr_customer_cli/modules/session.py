from injector import Module, provider, singleton

from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.session_store import SessionStore


class SessionModule(Module):
    """Session management module."""

    @singleton
    @provider
    def provide_session_store(
        self, logger: CliLogger, file_cache_service: FileCacheServiceInterface
    ) -> SessionStore:
        """
        Provide SessionStore instance.
        """
        return SessionStore(logger=logger, file_cache_service=file_cache_service)
