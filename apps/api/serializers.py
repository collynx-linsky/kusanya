"""
Serializers for the external API. Deliberately hand-written fields
(never `fields = "__all__"`) — build spec section 21: "Never expose
internal database implementation unnecessarily." Every serializer is
read-heavy; writes go through service-layer functions in the view, never
`serializer.save()` directly, so idempotency/audit/business rules are
never bypassed.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.billing.models import Bill, BillItem
from apps.control_numbers.models import ControlNumber
from apps.customers.models import Customer, CustomerAccount
from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.reconciliation.models import ReconciliationRun
from apps.settlement.models import SettlementBatch
from apps.tenants.models import Tenant
from apps.webhooks.models import WebhookEndpoint


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "sector", "status", "default_currency", "created_at"]
        read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "full_name", "email", "phone_number", "external_reference", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class CustomerAccountSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CustomerAccount
        fields = ["id", "customer", "name", "external_reference", "is_active", "created_at"]
        read_only_fields = ["id", "customer", "created_at"]


class BillItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillItem
        fields = ["description", "quantity", "unit_amount", "line_total"]
        read_only_fields = fields


class ControlNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = ControlNumber
        fields = ["id", "value", "scope", "status", "expires_at", "created_at"]
        read_only_fields = fields


class BillSerializer(serializers.ModelSerializer):
    items = BillItemSerializer(many=True, read_only=True)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    amount_paid = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    control_number = ControlNumberSerializer(read_only=True)

    class Meta:
        model = Bill
        fields = [
            "id", "bill_number", "status", "currency", "total_amount", "amount_paid", "balance",
            "due_date", "external_reference", "items", "control_number", "created_at",
        ]
        read_only_fields = [f for f in fields if f != "external_reference"]


class PaymentSerializer(serializers.ModelSerializer):
    control_number = serializers.CharField(source="control_number.value", read_only=True)
    bill_number = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id", "merchant_reference", "provider_reference", "status", "amount", "currency",
            "control_number", "bill_number", "payer_reference", "initiated_at", "completed_at",
            "failure_reason",
        ]
        read_only_fields = fields

    def get_bill_number(self, payment):
        bill = payment.control_number.bill
        return bill.bill_number if bill else None


class ReconciliationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationRun
        fields = [
            "id", "status", "started_at", "completed_at", "total_checked",
            "matched_count", "exception_count", "resolved_unknown_count",
        ]
        read_only_fields = fields


class SettlementBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettlementBatch
        fields = [
            "id", "reference", "period_start", "period_end", "gross_amount",
            "platform_fee_total", "provider_fee_total", "net_amount", "currency",
            "status", "settlement_date", "external_settlement_reference",
        ]
        read_only_fields = fields


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ["id", "url", "description", "is_active", "subscribed_events", "created_at"]
        read_only_fields = ["id", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "event_type", "channel", "recipient", "status", "sent_at", "created_at"]
        read_only_fields = fields


# --- Input validation for write endpoints -----------------------------
# Deliberately plain Serializers, not ModelSerializers with .save() —
# every write goes through a service function in the view, which is what
# actually creates the row (and enforces idempotency). These only
# validate the shape of the request body.


class CustomerCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    external_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class CustomerAccountCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    external_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class BillItemInputSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)


class BillCreateSerializer(serializers.Serializer):
    customer_account_id = serializers.UUIDField()
    items = BillItemInputSerializer(many=True)
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    external_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("A bill needs at least one item.")
        return items


class PaymentInitiateSerializer(serializers.Serializer):
    control_number = serializers.CharField(max_length=32)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    payer_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class WebhookEndpointCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    subscribed_events = serializers.ListField(child=serializers.CharField(), required=False, default=list)
