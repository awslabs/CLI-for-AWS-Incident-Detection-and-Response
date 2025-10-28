from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class SupportCaseAccessor(BaseAccessor):
    """Data Accessor for AWS support cases"""

    MAX_RETRIES = 5

    @inject
    def __init__(self, support_client: Any, logger: CliLogger) -> None:
        super().__init__(logger, "AWS Support API")
        self.client = support_client

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def create_support_case(
        self,
        subject: str,
        severity: str,
        category: str,
        communicationBody: str,
        issueType: str,
        attachmentSetId: str,
        language: str,
        serviceCode: str,
    ) -> str:
        """Create AWS Support Case"""
        try:
            response = self.client.create_case(
                subject=subject,
                serviceCode=serviceCode,
                severityCode=severity,
                categoryCode=category,
                communicationBody=communicationBody,
                language=language,
                issueType=issueType,
                attachmentSetId=attachmentSetId,
            )
            case_id = response.get("caseId")
            if not case_id:
                raise ValueError(
                    "AWS Support API response missing required field: caseId"
                )
            return str(case_id)

        except ClientError as exception:
            self._handle_error(exception, "create_support_case")
            raise
        except Exception as e:
            self.logger.error(f"Failed to create support case: {str(e)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def add_attachments_to_set(
        self, attachments: List[Dict[str, Any]], attachment_set_id: Optional[str] = None
    ) -> str:
        """
        Add attachments to a set for AWS Support case.
        AWS API limit: Maximum 3 attachments per attachment set (total, not per call).
        """
        try:
            params: Dict[str, Any] = {"attachments": attachments}
            if attachment_set_id is not None:
                params["attachmentSetId"] = attachment_set_id
            response = self.client.add_attachments_to_set(**params)
            attachment_set_id_val = response.get("attachmentSetId")
            if not attachment_set_id_val:
                raise ValueError(
                    "AWS Support API response missing required field: attachmentSetId"
                )
            return str(attachment_set_id_val)
        except ClientError as exception:
            self._handle_error(exception, "add_attachments_to_set")
            raise
        except Exception as e:
            self.logger.error(f"Failed to add attachments to set: {str(e)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_cases(
        self,
        case_id_list: Optional[List[str]] = None,
        display_id: Optional[str] = None,
        after_time: Optional[str] = None,
        before_time: Optional[str] = None,
        include_resolved_cases: Optional[bool] = None,
        language: Optional[str] = None,
        include_communications: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Describe AWS Support Cases with optional parameters"""
        try:
            result = []
            paginator = self.client.get_paginator("describe_cases")
            params: Dict[str, Any] = {}
            if case_id_list is not None:
                params["caseIdList"] = case_id_list
            if display_id is not None:
                params["displayId"] = display_id
            if after_time is not None:
                params["afterTime"] = after_time
            if before_time is not None:
                params["beforeTime"] = before_time
            if include_resolved_cases is not None:
                params["includeResolvedCases"] = include_resolved_cases
            if language is not None:
                params["language"] = language
            if include_communications is not None:
                params["includeCommunications"] = include_communications
            for page in paginator.paginate(**params):
                result.extend(page.get("cases", []))
            return result
        except ClientError as exception:
            self._handle_error(exception, "describe_cases")
            raise
        except Exception as e:
            self.logger.error(f"Failed to describe cases: {str(e)}")
            raise

    @retry(exceptions=ClientError, tries=3, delay=65, backoff=1, logger=None)
    def add_communication_to_case(
        self,
        case_id: str,
        body: str,
        attachment_set_id: Optional[str] = None,
        cc_email_addresses: Optional[List[str]] = None,
    ) -> None:
        """Add communication to an AWS Support Case with throttling protection.

        Retry configuration:
        - tries=3: Maximum 3 attempts
        - delay=65: 65 second delay between retries (AWS requires 60s minimum)
        - backoff=1: No exponential backoff (constant 65s delay)

        The 65s delay handles both retries and rate limiting between successive calls.
        """
        try:
            params: Dict[str, Any] = {"caseId": case_id, "communicationBody": body}
            if attachment_set_id is not None:
                params["attachmentSetId"] = attachment_set_id
            if cc_email_addresses is not None:
                params["ccEmailAddresses"] = cc_email_addresses
            response = self.client.add_communication_to_case(**params)
            result = response.get("result")
            if not result:
                raise ValueError(
                    f"AWS Support API failed to add communication to case {case_id}. "
                    f"API returned result=False, indicating the operation was unsuccessful."
                )
        except ClientError as exception:
            self._handle_error(exception, "add_communication_to_case")
            raise
        except Exception as e:
            self.logger.error(f"Failed to add communication to case: {str(e)}")
            raise
