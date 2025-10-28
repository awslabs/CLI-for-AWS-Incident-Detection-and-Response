import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)
EventBusName = os.environ["EnvEventBusName"]
# Get incident path from environment variable for flexible updates
INCIDENT_PATH = os.environ.get("INCIDENT_PATH", 'alert["labels"]["alertname"]')


def _parse_text_format(message: str) -> dict:
    """Parse text format to extract alert information."""
    alerts = []

    # Split by double newlines to separate alert blocks
    blocks = message.split("\n\n")

    for block in blocks:
        if "alertname =" in block:
            # Extract alertname from "- alertname = value" pattern
            for line in block.split("\n"):
                if "alertname =" in line:
                    alertname = line.split("alertname =", 1)[1].strip()
                    alerts.append({"labels": {"alertname": alertname}})
                    break

    # Fallback: if no alertname found, use original behavior
    if not alerts:
        alerts = [{"labels": {"alertname": message.strip()}}]

    return {"alerts": alerts}


def lambda_handler(event: dict, context: object) -> None:
    logger.info(event)
    # Set the event["detail"]["incident-detection-response-identifier"] value
    # to the name of your alert that is coming from your APM.

    for record in event["Records"]:
        try:
            message = record["Sns"]["Message"]

            # Support both JSON and text payload formats
            alert_data = None
            if isinstance(message, str):
                try:
                    # Try to parse as JSON first
                    alert_data = json.loads(message)
                except json.JSONDecodeError:
                    # If JSON parsing fails, treat as text payload
                    logger.info("Processing text payload format")
                    alert_data = _parse_text_format(message)
            else:
                alert_data = message

            if "alerts" not in alert_data:
                logger.error("No 'alerts' field found in the message")
                continue

            for alert in alert_data["alerts"]:
                try:
                    # Check if required fields exist
                    if "labels" not in alert:
                        logger.error("No 'labels' field found in alert")
                        continue

                    if "alertname" not in alert["labels"]:
                        logger.error("No 'alertname' field found in labels")
                        continue

                    # Use environment variable for incident path
                    try:
                        identifier = eval(INCIDENT_PATH)
                    except Exception as e:
                        logger.error(
                            f"Error evaluating incident path '{INCIDENT_PATH}': {e}"
                        )
                        # Fallback to default path
                        identifier = alert["labels"]["alertname"]

                    detail = {
                        "incident-detection-response-identifier": identifier,
                        "original_message": message,
                    }
                    client = boto3.client("events")
                    client.put_events(
                        Entries=[
                            {
                                "Detail": json.dumps(detail),
                                # Do not modify. This DetailType value is required.
                                "DetailType": "ams.monitoring/generic-apm",
                                # Do not modify. This Source value is required.
                                "Source": "GenericAPMEvent",
                                # Do not modify. This variable is set at the top
                                # of this code as a global variable. Change the
                                # variable value for your eventbus name at the
                                # top of this code.
                                "EventBusName": EventBusName,
                            }
                        ]
                    )

                    # logger.info(f"Sending payload to EventBridge: {detail}")
                    logger.info(
                        "EventBridge event payload: %s",
                        json.dumps(
                            {
                                "Detail": json.dumps(detail),
                                "DetailType": "ams.monitoring/generic-apm",
                                "Source": "GenericAPMEvent",
                                "EventBusName": EventBusName,
                            },
                            indent=2,
                        ),
                    )

                except KeyError as e:
                    logger.error(f"Key error while processing alert: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error while processing alert: {e}")
                    continue

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SNS message as JSON: {e}")
            continue
        except KeyError as e:
            logger.error(f"Missing required field in record: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error processing record: {e}")
            continue
