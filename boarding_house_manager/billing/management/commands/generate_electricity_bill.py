# billing/management/commands/generate_electricity_bill.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from billing.models import Tenant, Bill, ElectricityReading
from decimal import Decimal

class Command(BaseCommand):
    help = 'Generates an electricity bill for a tenant based on a new meter reading.'

    def add_arguments(self, parser):
        parser.add_argument('tenant_id', type=int, help='The ID of the tenant.')
        parser.add_argument('current_reading_value', type=Decimal, help='The current meter reading value (e.g., in kWh).')
        parser.add_argument('unit_price', type=Decimal, help='The price per unit (e.g., per kWh).')
        parser.add_argument('--reading_date', type=str, help='Date of the reading (YYYY-MM-DD). Defaults to today.', default=timezone.now().strftime('%Y-%m-%d'))

    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        current_reading_value = options['current_reading_value']
        unit_price = options['unit_price']
        reading_date_str = options['reading_date']

        try:
            reading_date = timezone.datetime.strptime(reading_date_str, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f"Date format for --reading_date should be YYYY-MM-DD. You provided: {reading_date_str}")

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise CommandError(f'Tenant with ID "{tenant_id}" does not exist.')

        if not tenant.is_active:
            self.stdout.write(self.style.WARNING(f'Warning: Tenant {tenant.full_name} (ID: {tenant_id}) is not active.'))
            # Decide if you want to stop or allow billing for inactive tenants

        # Find the latest electricity reading for this tenant that has been billed
        # to use as the previous reading.
        last_billed_reading = ElectricityReading.objects.filter(
            tenant=tenant,
            is_billed=True
        ).order_by('-reading_date', '-created_at').first()

        previous_reading_value_for_calc = Decimal('0.00')
        if last_billed_reading:
            previous_reading_value_for_calc = last_billed_reading.reading_value
            if current_reading_value < previous_reading_value_for_calc:
                raise CommandError(
                    f"Current reading ({current_reading_value}) cannot be less than the previous billed reading "
                    f"({previous_reading_value_for_calc}) from {last_billed_reading.reading_date}."
                )
        else:
            # This is the first reading being entered for this tenant, or no previous reading was billed.
            # Consumption will be the full current_reading_value, assuming meter started at 0 or was reset.
            # Or, you might require an initial reading to be entered manually.
            self.stdout.write(self.style.NOTICE(f"No previous billed reading found for {tenant.full_name}. Assuming this is the first reading period or starting from zero."))


        consumption = current_reading_value - previous_reading_value_for_calc
        if consumption < 0: # Should be caught above, but as a safeguard
            raise CommandError(f"Calculated consumption ({consumption}) is negative. Check readings.")

        bill_amount = consumption * unit_price

        # Create the new ElectricityReading entry
        new_reading = ElectricityReading.objects.create(
            tenant=tenant,
            reading_date=reading_date,
            reading_value=current_reading_value,
            previous_reading_value=previous_reading_value_for_calc if last_billed_reading else None,
            consumption=consumption,
            unit_price=unit_price,
            is_billed=True # Mark as billed immediately as we are creating the bill
        )

        # Create the Bill entry
        # Determine due date (e.g., 15 days from reading date)
        due_date = reading_date + timezone.timedelta(days=15)
        bill_description = (
            f"Electricity charge for period ending {reading_date}. "
            f"Current reading: {current_reading_value} kWh, "
            f"Previous reading: {new_reading.previous_reading_value or 'N/A'} kWh. "
            f"Consumption: {consumption} kWh @ {unit_price}/kWh."
        )

        bill = Bill.objects.create(
            tenant=tenant,
            bill_type='Electricity',
            amount=bill_amount,
            due_date=due_date,
            description=bill_description,
            is_paid=False
        )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created electricity reading and bill for {tenant.full_name} (Tenant ID: {tenant_id}).\n"
            f"Reading ID: {new_reading.id}, Bill ID: {bill.id}, Amount: {bill.amount}"
        ))
