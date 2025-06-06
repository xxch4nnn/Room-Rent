# billing/management/commands/generate_rent_bills.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from billing.models import Tenant, Bill, Room
from decimal import Decimal
import calendar

class Command(BaseCommand):
    help = 'Generates monthly rent bills for active tenants with assigned rooms and valid leases.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month', type=int, help='The month (1-12) for which to generate rent bills. Defaults to the current month.'
        )
        parser.add_argument(
            '--year', type=int, help='The year (YYYY) for which to generate rent bills. Defaults to the current year.'
        )
        parser.add_argument(
            '--due_days', type=int, default=5, help='Number of days from the start of the month for the rent bill to be due (e.g., 5 means due on the 5th).'
        )
        parser.add_argument(
            '--force', action='store_true', help='Force generation even if a rent bill for the period might exist (use with caution).'
        )

    def handle(self, *args, **options):
        now = timezone.now()
        month = options['month'] if options['month'] else now.month
        year = options['year'] if options['year'] else now.year
        due_days = options['due_days']
        force_generation = options['force']

        if not (1 <= month <= 12):
            raise CommandError("Month must be between 1 and 12.")
        if year < 2000 or year > now.year + 5: # Basic sanity check
            raise CommandError(f"Year {year} seems unlikely. Please specify a valid year.")

        # Rent is typically for the period of the specified month.
        # Bill generation usually happens at the start of the month or slightly before.
        bill_generation_date = timezone.datetime(year, month, 1).date() # Assuming rent bill is for the month starting this date
        month_name = calendar.month_name[month]

        # Find tenants who should be billed:
        # - Active status
        # - Assigned to a room
        # - Lease is active for the billing period (at least some part of the month)
        #   For simplicity, we'll bill if their lease_start_date is on or before the
        #   first day of the billing month, AND (their lease_end_date is null OR
        #   their lease_end_date is on or after the first day of the billing month).
        #   More complex pro-rating for mid-month move-in/out can be added later.

        active_tenants = Tenant.objects.filter(
            is_active=True,
            room__isnull=False, # Must have an assigned room
            lease_start_date__lte=bill_generation_date
        ).exclude(
            # Exclude if lease_end_date is set AND it's before the start of the billing month
            lease_end_date__isnull=False,
            lease_end_date__lt=bill_generation_date
        )

        # Further filter: ensure room has base_rent > 0
        tenants_to_bill = [
            tenant for tenant in active_tenants
            if tenant.room.base_rent is not None and tenant.room.base_rent > Decimal('0.00')
        ]


        if not tenants_to_bill:
            self.stdout.write(self.style.NOTICE(f"No active tenants found eligible for rent billing for {month_name} {year}."))
            return

        bills_created_count = 0
        bills_skipped_count = 0

        for tenant in tenants_to_bill:
            rent_amount = tenant.room.base_rent
            bill_description = f"Room Rent for {month_name} {year} (Room {tenant.room.room_number})."

            # Due date is typically early in the month, e.g., 1st or 5th.
            # If due_days is 0, it means due on the 1st. If 4, due on the 5th.
            # The problem description says due_days is "number of days from the start of the month",
            # so if due_days is 5, it means due on the 5th.
            # If bill_generation_date is the 1st, then due_date = 1st + 5 days which is the 6th.
            # This should be: due_date = bill_generation_date + timedelta(days=due_days -1) if we want it on the Nth day.
            # Or, more simply, if due_days = 5, it means the 5th day of the month.
            # Let's use due_date = timezone.datetime(year, month, due_days).date()
            # However, the previous commands used bill_generation_date (1st of month) + timedelta(days=due_days)
            # Let's keep it consistent: if due_days is 5, due date is 1st + 5 days = 6th.
            # If user wants it due ON the 5th, they'd pass due_days=4.
            # The help text says: "Number of days from the start of the month for the rent bill to be due (e.g., 5 means due on the 5th)."
            # This implies if due_days = 5, the due date *is* the 5th.
            # So, we should construct the date as timezone.datetime(year, month, due_days).date()
            # But we must handle if due_days makes it go to next month (e.g. due_days=32) or is invalid (e.g. 0)
            # The default is 5. So due date = 5th of the month.

            try:
                due_date = timezone.datetime(year, month, due_days).date()
            except ValueError:
                raise CommandError(f"Invalid due_days value: {due_days}. It's not a valid day for {month_name} {year}.")


            if not force_generation:
                # Check if a rent bill for this tenant and this specific month/year already exists.
                # Using description for uniqueness check here.
                existing_bill_this_period = Bill.objects.filter(
                    tenant=tenant,
                    bill_type='Rent',
                    description__icontains=f"for {month_name} {year}" # Assumes consistent description
                ).exists()

                if existing_bill_this_period:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping rent bill for {tenant.full_name} for {month_name} {year}: Bill already exists."
                    ))
                    bills_skipped_count += 1
                    continue

            bill = Bill.objects.create(
                tenant=tenant,
                bill_type='Rent',
                amount=rent_amount,
                due_date=due_date,
                description=bill_description,
                is_paid=False
            )
            bills_created_count += 1
            self.stdout.write(self.style.SUCCESS(
                f"Created rent bill for {tenant.full_name} (ID: {bill.id}) for {month_name} {year}. Amount: {bill.amount}"
            ))

        if bills_created_count > 0:
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully created {bills_created_count} rent bill(s)."))
        if bills_skipped_count > 0:
            self.stdout.write(self.style.WARNING(f"Skipped {bills_skipped_count} rent bill(s) as they already existed."))
        if bills_created_count == 0 and bills_skipped_count == 0 and tenants_to_bill:
             self.stdout.write(self.style.NOTICE("No new rent bills were created (all may have existed or no tenants eligible)."))
