from injector import Binder, Module

from aws_idr_customer_cli.modules.accessors import AccessorsModule
from aws_idr_customer_cli.modules.base import BaseModule
from aws_idr_customer_cli.modules.boto_clients import BotoClientsModule
from aws_idr_customer_cli.modules.file_cache import FileCacheModule
from aws_idr_customer_cli.modules.input import InputModule
from aws_idr_customer_cli.modules.logging import LoggingModule
from aws_idr_customer_cli.modules.service_clients import ServiceClientsModule
from aws_idr_customer_cli.modules.session import SessionModule
from aws_idr_customer_cli.modules.validation import ValidationModule


class AppModule(Module):
    """Main application module."""

    def configure(self, binder: Binder) -> None:
        binder.install(BaseModule())
        binder.install(LoggingModule())
        binder.install(BotoClientsModule())
        binder.install(InputModule())
        binder.install(FileCacheModule())
        binder.install(SessionModule())
        binder.install(AccessorsModule())
        binder.install(ServiceClientsModule())
        binder.install(ValidationModule())
