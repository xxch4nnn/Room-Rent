# billing/views.py
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import Bill, Tenant, Room, Payment # Ensure Payment is imported
from decimal import Decimal

@staff_member_required
def financial_summary_report(request):
    today = timezone.now().date()
    current_month_start = today.replace(day=1)

    total_unpaid = Bill.objects.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    paid_this_month_qs = Payment.objects.filter(payment_date__gte=current_month_start)
    total_paid_this_month = paid_this_month_qs.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    context = {
        'title': 'Financial Summary Report',
        'total_unpaid_all_time': total_unpaid,
        'total_paid_this_month': total_paid_this_month,
        'current_month_name': current_month_start.strftime("%B %Y"),
        'has_permission': request.user.has_perm('billing.view_bill') and request.user.has_perm('billing.view_payment'),
        'app_label': 'billing', # For breadcrumbs if needed by base template
    }
    return render(request, 'admin/billing/reports/financial_summary.html', context)

@staff_member_required
def occupancy_report(request):
    total_rooms = Room.objects.count()

    active_tenant_room_ids = Tenant.objects.filter(
        is_active=True,
        room__isnull=False
    ).values_list('room_id', flat=True).distinct()
    occupied_rooms_count = len(active_tenant_room_ids)

    vacant_rooms_count = Room.objects.exclude(id__in=active_tenant_room_ids).count()
    occupancy_rate = (occupied_rooms_count / total_rooms * 100) if total_rooms > 0 else 0

    context = {
        'title': 'Occupancy Report',
        'total_rooms': total_rooms,
        'occupied_rooms_count': occupied_rooms_count,
        'vacant_rooms_count': vacant_rooms_count,
        'occupancy_rate': f"{occupancy_rate:.2f}%",
        'has_permission': request.user.has_perm('billing.view_room') and request.user.has_perm('billing.view_tenant'),
        'app_label': 'billing', # For breadcrumbs
    }
    return render(request, 'admin/billing/reports/occupancy_report.html', context)
