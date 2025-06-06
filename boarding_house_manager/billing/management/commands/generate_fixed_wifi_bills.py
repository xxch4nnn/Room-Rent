# billing/management/commands/generate_fixed_wifi_bills.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from billing.models import Tenant, Bill
from decimal import Decimal
import calendar

class Command(BaseCommand):
    help = 'Generates fixed monthly WiFi bills for active tenants who have a specified fixed WiFi charge.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month', type=int, help='The month (1-12) for which to generate bills. Defaults to the current month.'
        )
        parser.add_argument(
            '--year', type=int, help='The year (YYYY) for which to generate bills. Defaults to the current year.'
        )
        parser.add_argument(
            '--due_days', type=int, default=15, help='Number of days from the start of the month for the bill to be due.'
        )
        parser.add_argument(
            '--force', action='store_true', help='Force generation even if a bill for the period might exist (use with caution).'
        )

    def handle(self, *args, **options):
        now = timezone.now()
        month = options['month'] if options['month'] else now.month
        year = options['year'] if options['year'] else now.year
        due_days = options['due_days']
        force_generation = options['force']

        if not (1 <= month <= 12):
            raise CommandError("Month must be between 1 and 12.")
        if year < 2000 or year > now.year + 5:
            raise CommandError(f"Year {year} seems unlikely. Please specify a valid year.")

        bill_generation_date = timezone.datetime(year, month, 1).date()
        month_name = calendar.month_name[month]

        active_tenants = Tenant.objects.filter(is_active=True)
        tenants_to_bill = [
            tenant for tenant in active_tenants
            if tenant.fixed_wifi_charge is not None and tenant.fixed_wifi_charge > Decimal('0.00')
        ]

        if not tenants_to_bill:
            self.stdout.write(self.style.NOTICE("No active tenants found with a fixed WiFi charge greater than zero."))
            return

        bills_created_count = 0
        bills_skipped_count = 0

        for tenant in tenants_to_bill:
            bill_description = f"Monthly fixed WiFi charge for {month_name} {year}."
            due_date = bill_generation_date + timezone.timedelta(days=due_days)

            if not force_generation:
                existing_bill_this_period = Bill.objects.filter(
                    tenant=tenant,
                    bill_type='WiFi',
                    description__icontains=f"for {month_name} {year}"
                ).exists()

                if existing_bill_this_period:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping WiFi bill for {tenant.full_name} for {month_name} {year}: Bill already exists."
                    ))
                    bills_skipped_count += 1
                    continue

            bill = Bill.objects.create(
                tenant=tenant,
                bill_type='WiFi',
                amount=tenant.fixed_wifi_charge,
                due_date=due_date,
                description=bill_description,
                is_paid=False
            )
            bills_created_count += 1
            self.stdout.write(self.style.SUCCESS(
                f"Created WiFi bill for {tenant.full_name} (ID: {bill.id}) for {month_name} {year}. Amount: {bill.amount}"
            ))

        if bills_created_count > 0:
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully created {bills_created_count} WiFi bill(s)."))
        if bills_skipped_count > 0:
            self.stdout.write(self.style.WARNING(f"Skipped {bills_skipped_count} WiFi bill(s) as they already existed."))
        if bills_created_count == 0 and bills_skipped_count == 0 and tenants_to_bill:
             self.stdout.write(self.style.NOTICE("No new WiFi bills were created (all may have existed or no tenants eligible)."))
