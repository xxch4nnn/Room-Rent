# billing/management/commands/generate_fixed_water_bills.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from billing.models import Tenant, Bill
from decimal import Decimal
import calendar

class Command(BaseCommand):
    help = 'Generates fixed monthly water bills for active tenants who have a specified fixed water charge.'

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
        if year < 2000 or year > now.year + 5: # Basic sanity check for year
            raise CommandError(f"Year {year} seems unlikely. Please specify a valid year.")

        # Determine the first and last day of the target month for checking existing bills
        _, last_day_of_month = calendar.monthrange(year, month)
        start_of_billing_period = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
        end_of_billing_period = timezone.datetime(year, month, last_day_of_month, 23, 59, 59, tzinfo=timezone.get_current_timezone())

        # Bill generation day (e.g. 1st of the month)
        bill_generation_date = timezone.datetime(year, month, 1).date()


        active_tenants = Tenant.objects.filter(is_active=True)
        tenants_to_bill = [
            tenant for tenant in active_tenants
            if tenant.fixed_water_charge is not None and tenant.fixed_water_charge > Decimal('0.00')
        ]

        if not tenants_to_bill:
            self.stdout.write(self.style.NOTICE("No active tenants found with a fixed water charge greater than zero."))
            return

        bills_created_count = 0
        bills_skipped_count = 0

        for tenant in tenants_to_bill:
            # Check if a water bill for this tenant and period already exists
            # We check based on the bill type and if the due date falls within the target month/year for simplicity.
            # A more robust check might involve custom fields on the Bill model like 'billing_period_start' and 'billing_period_end'.

            # For this command, we'll check if a water bill for this tenant was created *on* the 1st of the target month.
            # This assumes the command is run once per month.
            # A more robust check: does a water bill exist for this tenant for this billing period (month/year)?
            # This can be tricky if due dates are flexible. For now, we'll check if a bill *created* this month exists.

            # Simpler check: has a water bill been created for this tenant with a due date in the target month?
            # This might be too broad if due dates are very flexible.
            # Let's check if a bill for this tenant for 'Water' for this specific month/year already exists.
            # We can add a convention to the description.

            bill_description = f"Monthly fixed water charge for {calendar.month_name[month]} {year}."
            due_date = bill_generation_date + timezone.timedelta(days=due_days)


            if not force_generation:
                existing_bill_this_period = Bill.objects.filter(
                    tenant=tenant,
                    bill_type='Water',
                    # A simple check for description can work if standardized
                    description__icontains=f"for {calendar.month_name[month]} {year}"
                    # Or, more robustly, by checking due_date range or a dedicated period field
                    # due_date__year=year,
                    # due_date__month=month
                ).exists()

                if existing_bill_this_period:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping water bill for {tenant.full_name} for {calendar.month_name[month]} {year}: Bill already exists."
                    ))
                    bills_skipped_count += 1
                    continue

            bill = Bill.objects.create(
                tenant=tenant,
                bill_type='Water',
                amount=tenant.fixed_water_charge,
                due_date=due_date,
                description=bill_description,
                is_paid=False
            )
            bills_created_count += 1
            self.stdout.write(self.style.SUCCESS(
                f"Created water bill for {tenant.full_name} (ID: {bill.id}) for {calendar.month_name[month]} {year}. Amount: {bill.amount}"
            ))

        if bills_created_count > 0:
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully created {bills_created_count} water bill(s)."))
        if bills_skipped_count > 0:
            self.stdout.write(self.style.WARNING(f"Skipped {bills_skipped_count} water bill(s) as they already existed."))
        if bills_created_count == 0 and bills_skipped_count == 0 and tenants_to_bill:
             self.stdout.write(self.style.NOTICE("No new water bills were created (all may have existed or no tenants eligible)."))
