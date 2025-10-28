"""Alarm contact data collection utilities."""

from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any, Callable, Dict, Optional

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import (
    MissingInputFieldError,
    ValidationError,
)
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmContacts,
    ContactInfo,
    OnboardingSubmission,
)
from aws_idr_customer_cli.utils.validation.validator import (
    validate_contact_email,
    validate_contact_name,
    validate_contact_phone,
    validate_escalation_email_unique,
    validate_escalation_phone_unique,
)

# Maximum retries for validation
MAX_RETRIES = 3


class ContactType(Enum):
    PRIMARY = "primary"
    ESCALATION = "escalation"


class FieldType(Enum):
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"


@dataclass
class ContactField:
    contact_type: ContactType
    field_type: FieldType
    display_name: str
    validator: Callable[[Any], Any]

    @property
    def key(self) -> str:
        return f"{self.contact_type.value}_{self.field_type.value}"


class AlarmContactValidator:
    """Factory for creating contact validators."""

    @staticmethod
    def create_unique_email_validator(
        primary_contact: ContactInfo,
    ) -> Callable[[Any], Any]:
        return partial(
            validate_escalation_email_unique, primary_contact=primary_contact
        )

    @staticmethod
    def create_unique_phone_validator(
        primary_contact: ContactInfo,
    ) -> Callable[[Any], Any]:
        return partial(
            validate_escalation_phone_unique, primary_contact=primary_contact
        )


class AlarmContactFieldManager:
    """Manages contact field operations."""

    def __init__(self, contacts: AlarmContacts):
        self.contacts = contacts
        self._field_definitions: Optional[Dict[str, ContactField]] = None

    def get_field_definitions(self) -> Dict[str, ContactField]:
        """Get field definitions with appropriate validators."""
        if self._field_definitions is None:
            self._field_definitions = {
                "primary_name": ContactField(
                    ContactType.PRIMARY,
                    FieldType.NAME,
                    "Primary contact name",
                    validate_contact_name,
                ),
                "primary_email": ContactField(
                    ContactType.PRIMARY,
                    FieldType.EMAIL,
                    "Primary contact email",
                    validate_contact_email,
                ),
                "primary_phone": ContactField(
                    ContactType.PRIMARY,
                    FieldType.PHONE,
                    "Primary contact phone (optional)",
                    validate_contact_phone,
                ),
                "escalation_name": ContactField(
                    ContactType.ESCALATION,
                    FieldType.NAME,
                    "Escalation contact name",
                    validate_contact_name,
                ),
                "escalation_email": ContactField(
                    ContactType.ESCALATION,
                    FieldType.EMAIL,
                    "Escalation contact email",
                    AlarmContactValidator.create_unique_email_validator(
                        self.contacts.primary_contact
                    ),
                ),
                "escalation_phone": ContactField(
                    ContactType.ESCALATION,
                    FieldType.PHONE,
                    "Escalation contact phone (optional)",
                    AlarmContactValidator.create_unique_phone_validator(
                        self.contacts.primary_contact
                    ),
                ),
            }
        return self._field_definitions

    def get_field_value(self, field_key: str) -> str:
        """Get current value of a field."""
        contact_type, field_type = field_key.split("_", 1)
        contact = (
            self.contacts.primary_contact
            if contact_type == "primary"
            else self.contacts.escalation_contact
        )
        return getattr(contact, field_type, "")

    def set_field_value(self, field_key: str, value: str) -> None:
        """Set value of a field."""
        contact_type, field_type = field_key.split("_", 1)
        contact = (
            self.contacts.primary_contact
            if contact_type == "primary"
            else self.contacts.escalation_contact
        )
        setattr(contact, field_type, value)


def prompt_with_validation_for_contact(
    ui: InteractiveUI,
    prompt: str,
    validator: Callable[[Any], Any],
    current_value: str = "",
    helper_text: Optional[str] = None,
) -> Any:
    """Prompt with validation and retry on error for contact fields."""
    for attempt in range(MAX_RETRIES):
        try:
            # Display helper text if provided (only on first attempt)
            if helper_text and attempt == 0:
                ui.display_info(helper_text, style="dim")

            value = ui.prompt_input(prompt, current_value)
            return validator(value)
        except ValidationError as e:
            ui.display_error(str(e))
            if attempt == MAX_RETRIES - 1:  # Last attempt
                raise
            # Continue to next attempt

    # This should never be reached, but just in case
    raise ValidationError("Maximum retry attempts exceeded")


def display_alarm_contact_header_and_info(
    ui: InteractiveUI, contact_type: ContactType
) -> None:
    """Display header and info message based on contact type."""
    contact_name = contact_type.value.title()
    ui.display_header(f"📞 {contact_name} Incident Contact Information")

    if contact_type == ContactType.PRIMARY:
        info_message = (
            "Primary incident contact serves as the initial point of contact "
            "for AWS IDR incident and alarm notifications."
        )
    else:
        info_message = (
            "Escalation contact will be contacted if primary contact is "
            "unreachable during an incident."
        )

    ui.display_info(info_message)


def collect_contact_fields(
    ui: InteractiveUI,
    contact_type: ContactType,
    field_manager: AlarmContactFieldManager,
) -> bool:
    field_definitions = field_manager.get_field_definitions()
    for field_key, field_def in field_definitions.items():
        if field_def.contact_type != contact_type:
            continue

        current_value = field_manager.get_field_value(field_key)

        helper_text = None
        if field_def.field_type == FieldType.PHONE:
            helper_text = (
                "📱 Format examples: +1-555-123-4567, (555) 123-4567, +44 20 7946 0958"
            )

        try:
            value = prompt_with_validation_for_contact(
                ui=ui,
                prompt=field_def.display_name,
                validator=field_def.validator,
                current_value=current_value,
                helper_text=helper_text,
            )
            if value is None:
                return False
            field_manager.set_field_value(field_key, value)
        except (MissingInputFieldError, ValidationError):
            return False

    return True


def ensure_alarm_contacts(submission: OnboardingSubmission) -> AlarmContacts:
    """Ensure alarm_contacts exists or is initialized."""
    if not submission:
        raise RuntimeError("No submission available")

    if not submission.alarm_contacts:
        submission.alarm_contacts = AlarmContacts(
            primary_contact=ContactInfo(name="", email="", phone=""),
            escalation_contact=ContactInfo(name="", email="", phone=""),
        )

    return submission.alarm_contacts


def _are_alarm_contacts_present(contacts: AlarmContacts) -> bool:
    """Check if both primary and escalation alarm contacts have valid name and email."""
    if not contacts:
        return False

    for contact in [contacts.primary_contact, contacts.escalation_contact]:
        if not contact or not all([contact.name, contact.email]):
            return False

    return True


def collect_alarm_contact_info(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
) -> bool:
    """Collect primary and escalation alarm contact information."""
    if not submission:
        raise RuntimeError("No submission available")

    if _are_alarm_contacts_present(contacts=submission.alarm_contacts):
        ui.display_info(
            "✅ Alarm Contact Information Found. "
            "Using already existing alarm contact information. Proceeding to next step"
        )
        return True

    contacts = ensure_alarm_contacts(submission)
    field_manager = AlarmContactFieldManager(contacts)

    display_alarm_contact_header_and_info(ui, ContactType.PRIMARY)
    if not collect_contact_fields(ui, ContactType.PRIMARY, field_manager):
        return False

    display_alarm_contact_header_and_info(ui, ContactType.ESCALATION)

    # Reset field definitions to regenerate validators with updated primary contact info
    field_manager._field_definitions = None

    if not collect_contact_fields(ui, ContactType.ESCALATION, field_manager):
        return False

    ui.display_info("✅ Alarm contact information collected")
    return True


def display_alarm_contact_summary(
    ui: InteractiveUI, submission: OnboardingSubmission
) -> None:
    """Display alarm contact information summary."""
    if not submission or not submission.alarm_contacts:
        ui.display_warning("No alarm contact information available")
        return

    contacts = submission.alarm_contacts
    ui.display_result(
        "Alarm Contact Information Summary",
        {
            "Primary Name": contacts.primary_contact.name,
            "Primary Email": contacts.primary_contact.email,
            "Primary Phone": contacts.primary_contact.phone or "(not provided)",
            "Escalation Name": contacts.escalation_contact.name,
            "Escalation Email": contacts.escalation_contact.email,
            "Escalation Phone": contacts.escalation_contact.phone or "(not provided)",
        },
    )


def offer_alarm_contact_correction_workflow(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
) -> bool:
    """Offer user option to modify alarm contact information."""
    if not submission or not submission.alarm_contacts:
        return False

    wants_to_modify = ui.prompt_confirm(
        "Would you like to modify any alarm contact information?", False
    )
    if not wants_to_modify:
        return False

    field_manager = AlarmContactFieldManager(submission.alarm_contacts)
    field_definitions = field_manager.get_field_definitions()

    options = [
        f"{field_def.display_name}: {field_manager.get_field_value(field_key)}"
        for field_key, field_def in field_definitions.items()
    ]

    choice = ui.select_option(options, "Select alarm contact field to modify")
    if choice < 0 or choice >= len(options):
        return False

    field_key = list(field_definitions.keys())[choice]
    field_def = field_definitions[field_key]
    current_value = field_manager.get_field_value(field_key)

    helper_text = None
    if field_def.field_type == FieldType.PHONE:
        helper_text = (
            "📱 Format examples: +1-555-123-4567, (555) 123-4567, +44 20 7946 0958"
        )

    try:
        new_value = prompt_with_validation_for_contact(
            ui,
            prompt=field_def.display_name,
            validator=field_def.validator,
            current_value=current_value,
            helper_text=helper_text,
        )

        if new_value is not None:
            field_manager.set_field_value(field_key, new_value)
            ui.display_info(f"✅ {field_def.display_name} updated")

        return True
    except (MissingInputFieldError, ValidationError):
        return False
