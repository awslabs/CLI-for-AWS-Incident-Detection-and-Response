import functools
import json
import logging
import os
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

client = boto3.client("events")

DETAIL_TYPE = "ams.monitoring/generic-apm"  # Do not modify.
DETAIL_SOURCE = "GenericAPMEvent"  # Do not modify.
EVENTBUS_NAME_ENVIRONMENT_VALUE = "EnvEventBusName"  # Do not modify
# Get incident path from environment variable for flexible updates
INCIDENT_PATH = os.environ.get("INCIDENT_PATH", 'raw_json["detail"]["ProblemTitle"]')


class UnexpectedError(Exception):
    pass


class EnvironmentKeyError(Exception):
    pass


class EnvironmentError(Exception):
    pass


class EventBusPutError(Exception):
    pass


class ResponseError(Exception):
    pass


def catch_exceptions(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if self.response is not None and self.response != 200:
            return
        try:
            return func(self, *args, **kwargs)
        except ValueError as e:
            self.response = 400
            msg = f"{self.session_id}: ValueError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except KeyError as e:
            self.response = 400
            print(self.response)
            msg = f"{self.session_id}: KeyError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except EnvironmentKeyError as e:
            self.response = 500
            msg = f"{self.session_id}: EnvironmentKeyError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except EnvironmentError as e:
            self.response = 500
            msg = f"{self.session_id}: EnvironmentError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except EventBusPutError as e:
            self.response = 500
            msg = f"{self.session_id}: EventBusPutError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except ResponseError as e:
            self.response = 500
            msg = f"{self.session_id}: ResponseError in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)
        except Exception as e:
            self.response = 500
            msg = f"{self.session_id}: Unexpected error in {func.__name__}: {e}"
            self.error_message = msg
            logger.error(self.error_message, exc_info=True)

    return wrapper


class Transformations:
    def __init__(self, event: dict) -> None:
        self._session_id = str(uuid4())
        self._response: Optional[int] = None
        self.error_message = None
        self.event = event

        self.event_bus_name = self._get_eventbus_name()
        self.raw_json = self._add_idr_key_value()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def response(self) -> Optional[int]:
        return self._response

    @response.setter
    @catch_exceptions
    def response(self, value: int) -> None:
        try:
            self._response = int(value)
        except Exception as e:
            raise ResponseError(e)

    @catch_exceptions
    def _get_eventbus_name(self) -> Optional[str]:
        event_bus_name = None
        try:
            event_bus_name = os.environ[EVENTBUS_NAME_ENVIRONMENT_VALUE]
        except KeyError as e:
            raise EnvironmentKeyError(e)
        except Exception as e:
            raise EnvironmentError(e)
        return event_bus_name

    @catch_exceptions
    def _add_idr_key_value(self) -> Optional[Dict[str, Any]]:
        msg = f"{self.session_id}: Adding incident-detection-response-identifier"
        logger.info(msg)
        raw_json = None
        try:
            raw_json = json.loads(self.event["body"])
        except Exception:
            raw_json = self.event

        # Extract identifier from original payload structure
        incident_identifier = None
        try:
            incident_identifier = eval(INCIDENT_PATH)
        except Exception as e:
            logger.error(f"Error evaluating incident path '{INCIDENT_PATH}': {e}")
            # Try fallback paths based on common APM structures
            if "detail" in raw_json and "ProblemTitle" in raw_json["detail"]:
                incident_identifier = raw_json["detail"]["ProblemTitle"]
            elif "ProblemTitle" in raw_json:
                incident_identifier = raw_json["ProblemTitle"]
            else:
                raise KeyError(
                    f"Could not extract incident identifier from path '{INCIDENT_PATH}' "
                )

        # Prepare the structure for EventBridge
        idr_key = "incident-detection-response-identifier"

        # If payload already has 'detail', add the identifier to it
        if "detail" in raw_json:
            raw_json["detail"][idr_key] = incident_identifier
        else:
            # Wrap the entire payload in a detail field for EventBridge
            raw_json = {"detail": {**raw_json, idr_key: incident_identifier}}

        msg = f"{self.session_id}: Successfully added identifier: {raw_json}"
        logger.info(msg)
        return raw_json

    @catch_exceptions
    def put_event(self) -> None:
        if self.response is not None and self.response != 200:
            return
        msg = f"{self.session_id}: Putting event to eventbus using {self.raw_json}"
        print(f"{msg}. Current status code: {self.response}")
        response = client.put_events(
            Entries=[
                {
                    "Detail": json.dumps(self.raw_json["detail"], indent=2),
                    "DetailType": DETAIL_TYPE,  # Do not modify.
                    "Source": DETAIL_SOURCE,  # Do not modify.
                    "EventBusName": self.event_bus_name,  # Do not modify.
                }
            ]
        )
        if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
            logger.error(f"{self.session_id}: EventBus Put API Response: {response}")
            raise EventBusPutError(response)
        else:
            logger.info(f"{self.session_id}: EventBus Put API Response: {response}")
        self._response = response["ResponseMetadata"]["HTTPStatusCode"]


def create_api_gateway_response(
    transform_class_object: "Transformations",
) -> Dict[str, Any]:
    status_code = transform_class_object.response or 500
    if 200 <= status_code < 300:
        response_status = 200
        body = "Success"
    elif 400 <= status_code < 500:
        response_status = 400
        body = "Bad Request"
    else:
        response_status = 500
        body = "Internal Server Error"

    if response_status != 200:
        logger.error(f"Exit Error: {transform_class_object.error_message}")
    else:
        obj = transform_class_object
        msg = (
            f"{obj.session_id}: Successfully sent event to eventbus "
            f"{obj.event_bus_name}\\n"
            f"incident-detection-response-identifier:"
            f"{obj.raw_json['detail']['incident-detection-response-identifier']}\\n"
            f"DetailType:{DETAIL_TYPE}\\nSource:{DETAIL_SOURCE}"
        )
        logger.info(msg)

    response = {
        "statusCode": response_status,
        "body": json.dumps(body) if isinstance(body, dict) else str(body),
        "headers": {
            "Content-Type": "application/json",
        },
    }

    return response


def lambda_handler(event: dict, context: object) -> dict:
    logger.info(event)
    transformation = Transformations(event)
    if transformation.response is not None and transformation.response != 200:
        return create_api_gateway_response(transformation)
    transformation.put_event()
    return create_api_gateway_response(transformation)
