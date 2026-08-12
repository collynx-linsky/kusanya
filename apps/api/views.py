"""
External API views (build spec sections 21-22). Every write here calls
the same service-layer function the portal uses — apps.customers.services,
apps.billing.services, apps.control_numbers.services,
apps.payments.services — never a bare `serializer.save()`. That's what
makes API-originated idempotency (external_reference / Idempotency-Key)
and everything downstream of it (audit, revenue, webhooks, notifications)
identical whether a bill was created by a human in the portal or an ERP
calling this API.
"""

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.authentication import ApiKeyAuthentication
from apps.api.permissions import HasApiCredential
from apps.api.serializers import (
    BillCreateSerializer,
    BillSerializer,
    CustomerAccountCreateSerializer,
    CustomerAccountSerializer,
    CustomerCreateSerializer,
    CustomerSerializer,
    InstitutionSerializer,
    NotificationSerializer,
    PaymentInitiateSerializer,
    PaymentSerializer,
    ReconciliationRunSerializer,
    SettlementBatchSerializer,
    WebhookEndpointCreateSerializer,
    WebhookEndpointSerializer,
)
from apps.api.throttling import ApiCredentialRateThrottle
from apps.billing.models import Bill
from apps.billing.services import get_or_create_bill
from apps.control_numbers.services import get_or_create_for_bill
from apps.customers.models import Customer, CustomerAccount
from apps.customers.services import get_or_create_customer, get_or_create_customer_account
from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.payments.services import initiate_payment, query_payment
from apps.reconciliation.models import ReconciliationRun
from apps.settlement.models import SettlementBatch
from apps.webhooks.models import WebhookEndpoint


class ApiView(APIView):
    """Shared config for every external API view — see
    docs/API_ARCHITECTURE.md. Tenant is always `self.request.tenant`,
    set by ApiKeyAuthentication from the credential; every queryset below
    filters by it explicitly (same pattern as every portal view since
    Phase 2 — see docs/MULTI_TENANCY.md)."""

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiCredential]
    throttle_classes = [ApiCredentialRateThrottle]


# --- Institutions -----------------------------------------------------


class InstitutionMeView(ApiView, RetrieveAPIView):
    serializer_class = InstitutionSerializer

    def get_object(self):
        return self.request.tenant


# --- Customers ----------------------------------------------------------


class CustomerListCreateView(ApiView):
    def get(self, request):
        customers = Customer.objects.filter(tenant=request.tenant).order_by("-created_at")
        external_reference = request.query_params.get("external_reference")
        if external_reference:
            customers = customers.filter(external_reference=external_reference)
        return Response(CustomerSerializer(customers[:200], many=True).data)

    def post(self, request):
        input_serializer = CustomerCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        customer, created = get_or_create_customer(
            tenant=request.tenant,
            full_name=data["full_name"],
            email=data["email"],
            phone_number=data["phone_number"],
            external_reference=data["external_reference"],
        )
        return Response(
            CustomerSerializer(customer).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class CustomerDetailView(ApiView, RetrieveAPIView):
    serializer_class = CustomerSerializer

    def get_object(self):
        return get_object_or_404(Customer, pk=self.kwargs["pk"], tenant=self.request.tenant)


# --- Customer accounts --------------------------------------------------


class AccountListCreateView(ApiView):
    def get(self, request):
        accounts = CustomerAccount.objects.filter(tenant=request.tenant).order_by("-created_at")
        customer_id = request.query_params.get("customer_id")
        if customer_id:
            accounts = accounts.filter(customer_id=customer_id)
        return Response(CustomerAccountSerializer(accounts[:200], many=True).data)

    def post(self, request):
        input_serializer = CustomerAccountCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        customer = get_object_or_404(Customer, pk=data["customer_id"], tenant=request.tenant)
        account, created = get_or_create_customer_account(
            tenant=request.tenant,
            customer=customer,
            name=data["name"],
            external_reference=data["external_reference"],
        )
        return Response(
            CustomerAccountSerializer(account).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# --- Bills ----------------------------------------------------------------


class BillListCreateView(ApiView):
    def get(self, request):
        bills = Bill.objects.filter(tenant=request.tenant).select_related("control_number").order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            bills = bills.filter(status=status_filter)
        external_reference = request.query_params.get("external_reference")
        if external_reference:
            bills = bills.filter(external_reference=external_reference)
        return Response(BillSerializer(bills[:200], many=True).data)

    def post(self, request):
        input_serializer = BillCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        account = get_object_or_404(
            CustomerAccount, pk=data["customer_account_id"], tenant=request.tenant
        )
        bill, created = get_or_create_bill(
            tenant=request.tenant,
            customer_account=account,
            items=data["items"],
            due_date=data["due_date"],
            external_reference=data["external_reference"],
        )
        if created:
            from apps.billing.models import BillStatus

            bill.transition_to(BillStatus.ACTIVE)
        return Response(
            BillSerializer(bill).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class BillDetailView(ApiView, RetrieveAPIView):
    serializer_class = BillSerializer

    def get_object(self):
        return get_object_or_404(
            Bill.objects.select_related("control_number"), pk=self.kwargs["pk"], tenant=self.request.tenant
        )


class BillControlNumberView(ApiView):
    """POST is idempotent — the same rule as everywhere else this control
    number engine is called from: a bill that already has one gets it
    back, no duplicate, no second creation fee event."""

    def post(self, request, pk):
        bill = get_object_or_404(Bill, pk=pk, tenant=request.tenant)
        control_number, created = get_or_create_for_bill(tenant=request.tenant, bill=bill)
        from apps.api.serializers import ControlNumberSerializer

        return Response(
            ControlNumberSerializer(control_number).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# --- Payments ---------------------------------------------------------------


class PaymentListCreateView(ApiView):
    def get(self, request):
        payments = Payment.objects.filter(tenant=request.tenant).select_related("control_number").order_by(
            "-initiated_at"
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            payments = payments.filter(status=status_filter)
        return Response(PaymentSerializer(payments[:200], many=True).data)

    def post(self, request):
        input_serializer = PaymentInitiateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        from apps.control_numbers.models import ControlNumber
        from apps.providers.models import PaymentProvider

        control_number = get_object_or_404(
            ControlNumber, value=data["control_number"], tenant=request.tenant
        )
        # Phase 6 exposes only the mock/sandbox provider externally, same
        # as the portal — see docs/PAYMENT_PROVIDER_ARCHITECTURE.md; a
        # real provider would be selectable here once one exists.
        provider = get_object_or_404(PaymentProvider, code="mock")

        idempotency_key = request.headers.get("Idempotency-Key", "")
        payment = initiate_payment(
            tenant=request.tenant,
            control_number=control_number,
            provider=provider,
            amount=Decimal(data["amount"]),
            payer_reference=data["payer_reference"],
            idempotency_key=idempotency_key,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(ApiView, RetrieveAPIView):
    serializer_class = PaymentSerializer

    def get_object(self):
        return get_object_or_404(Payment, pk=self.kwargs["pk"], tenant=self.request.tenant)


class PaymentQueryView(ApiView):
    """Resolves an UNKNOWN payment — never a blind retry. See
    docs/PAYMENT_LIFECYCLE.md. Exposed via the API for the same reason
    the portal has a "Query provider" button: an ERP integration needs a
    way to ask "what actually happened" without initiating a new payment."""

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, tenant=request.tenant)
        query_payment(payment)
        return Response(PaymentSerializer(payment).data)


# --- Reconciliation (read-only) ------------------------------------------


class ReconciliationRunListView(ApiView, ListAPIView):
    serializer_class = ReconciliationRunSerializer

    def get_queryset(self):
        return ReconciliationRun.objects.filter(tenant=self.request.tenant).order_by("-started_at")[:100]


# --- Settlements (read-only) ----------------------------------------------


class SettlementBatchListView(ApiView, ListAPIView):
    serializer_class = SettlementBatchSerializer

    def get_queryset(self):
        return SettlementBatch.objects.filter(tenant=self.request.tenant).order_by("-period_end")[:100]


class SettlementBatchDetailView(ApiView, RetrieveAPIView):
    serializer_class = SettlementBatchSerializer

    def get_object(self):
        return get_object_or_404(SettlementBatch, pk=self.kwargs["pk"], tenant=self.request.tenant)


# --- Webhooks -----------------------------------------------------------


class WebhookEndpointListCreateView(ApiView):
    def get(self, request):
        endpoints = WebhookEndpoint.objects.filter(tenant=request.tenant).order_by("-created_at")
        return Response(WebhookEndpointSerializer(endpoints, many=True).data)

    def post(self, request):
        input_serializer = WebhookEndpointCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        endpoint = WebhookEndpoint.objects.create(
            tenant=request.tenant,
            url=data["url"],
            description=data["description"],
            subscribed_events=data["subscribed_events"],
        )
        # The signing secret is returned exactly once, at creation — same
        # rule as everywhere else a secret is generated in this codebase
        # (ADR-020-adjacent pattern: apps.api credentials, Phase 3
        # webhook endpoints created via the portal).
        payload = WebhookEndpointSerializer(endpoint).data
        payload["secret"] = endpoint.secret
        return Response(payload, status=status.HTTP_201_CREATED)


# --- Notifications (read-only) -------------------------------------------


class NotificationListView(ApiView, ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(tenant=self.request.tenant).order_by("-created_at")[:200]
