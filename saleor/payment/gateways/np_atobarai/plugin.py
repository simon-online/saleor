from typing import TYPE_CHECKING

import opentracing
from django.core.exceptions import ValidationError

from saleor.payment.gateways.np_atobarai import api
from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from saleor.plugins.error_codes import PluginErrorCode

from ..utils import require_active_plugin
from . import GatewayConfig, capture, process_payment, refund, void

GATEWAY_NAME = "NP後払い"

if TYPE_CHECKING:
    # flake8: noqa
    from saleor.plugins.models import PluginConfiguration

    from . import GatewayResponse, PaymentData


__all__ = ["NPAtobaraiGatewayPlugin"]


MERCHANT_CODE = "merchant_code"
SP_CODE = "sp_code"
TERMINAL_ID = "terminal_id"
USE_SANDBOX = "use_sandbox"


def get_api_config(conf) -> api.ApiConfig:
    return api.ApiConfig(
        test_mode=conf[USE_SANDBOX],
        merchant_code=conf[MERCHANT_CODE],
        sp_code=conf[SP_CODE],
        terminal_id=conf[TERMINAL_ID],
    )


class NPAtobaraiGatewayPlugin(BasePlugin):
    PLUGIN_ID = "mirumee.payments.np-atobarai"
    PLUGIN_NAME = GATEWAY_NAME
    CONFIGURATION_PER_CHANNEL = True
    SUPPORTED_CURRENCIES = "JPY"

    DEFAULT_CONFIGURATION = [
        {"name": MERCHANT_CODE, "value": None},
        {"name": SP_CODE, "value": None},
        {"name": TERMINAL_ID, "value": None},
        {"name": USE_SANDBOX, "value": True},
    ]

    CONFIG_STRUCTURE = {
        MERCHANT_CODE: {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide NP後払い Merchant Code.",
            "label": "Merchant Code",
        },
        SP_CODE: {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide NP後払い SP Code.",
            "label": "SP Code",
        },
        TERMINAL_ID: {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide NP後払い Terminal ID.",
            "label": "Terminal ID",
        },
        USE_SANDBOX: {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should use NP後払い sandbox API.",
            "label": "Use sandbox",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=False,
            supported_currencies=self.SUPPORTED_CURRENCIES,
            connection_params={
                "merchant_code": configuration[MERCHANT_CODE],
                "sp_code": configuration[SP_CODE],
                "terminal_id": configuration[TERMINAL_ID],
                "sandbox_mode": configuration[USE_SANDBOX],
            },
        )

    def _get_gateway_config(self) -> GatewayConfig:
        return self.config

    def capture_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return capture(payment_information, self._get_gateway_config())

    def refund_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return refund(payment_information, self._get_gateway_config())

    def void_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return void(payment_information, self._get_gateway_config())

    def process_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return process_payment(payment_information, self._get_gateway_config())

    def get_supported_currencies(self, previous_value):
        return self.SUPPORTED_CURRENCIES

    @classmethod
    def validate_authentication(cls, plugin_configuration: "PluginConfiguration"):
        conf = {
            data["name"]: data["value"] for data in plugin_configuration.configuration
        }
        with opentracing.global_tracer().start_active_span(
            "np-atobarai.utilities.ping"
        ) as scope:
            span = scope.span
            span.set_tag("service.name", "np-atobarai")
            response = api.health_check(get_api_config(conf))

        if not response:
            raise ValidationError(
                "Authentication failed. Please check provided data.",
                code=PluginErrorCode.PLUGIN_MISCONFIGURED.value,
            )

    @classmethod
    def validate_plugin_configuration(cls, plugin_configuration: "PluginConfiguration"):
        """Validate if provided configuration is correct."""
        missing_fields = []
        configuration = plugin_configuration.configuration
        configuration = {item["name"]: item["value"] for item in configuration}
        if not configuration[MERCHANT_CODE]:
            missing_fields.append(TERMINAL_ID)
        if not configuration[SP_CODE]:
            missing_fields.append(SP_CODE)
        if not configuration[TERMINAL_ID]:
            missing_fields.append(TERMINAL_ID)

        if plugin_configuration.active:
            if missing_fields:
                error_msg = (
                    "To enable a plugin, you need to provide values for the "
                    "following fields: "
                )
                raise ValidationError(
                    error_msg + ", ".join(missing_fields),
                    code=PluginErrorCode.PLUGIN_MISCONFIGURED.value,
                )

            cls.validate_authentication(plugin_configuration)
