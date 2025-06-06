from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from billing.models import Bill, Tenant # Assuming models are in ..models
import datetime

class Command(BaseCommand):
    help = 'Sends upcoming due date and overdue bill reminders to tenants via email.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--upcoming_days', type=int, default=3,
            help='Number of days in advance to send upcoming due reminders.'
        )
        parser.add_argument(
            '--test_email', type=str, help='Send all reminders to this email address for testing.'
        )
        parser.add_argument(
            '--dry_run', action='store_true', help="Run the command without actually sending emails."
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        upcoming_days = options['upcoming_days']
        test_email_recipient = options['test_email']
        dry_run = options['dry_run']

        upcoming_due_date = today + datetime.timedelta(days=upcoming_days)

        # --- Upcoming Bill Reminders ---
        upcoming_bills = Bill.objects.filter(
            is_paid=False,
            due_date=upcoming_due_date,
            tenant__is_active=True, # Only active tenants
            tenant__email__isnull=False # Ensure tenant has an email
        ).exclude(tenant__email__exact='').select_related('tenant') # Optimize tenant query

        self.stdout.write(self.style.SUCCESS(f"Processing reminders for {today}:"))
        self.stdout.write(f"Found {upcoming_bills.count()} bill(s) due in {upcoming_days} day(s) (on {upcoming_due_date}).")

        sent_upcoming_count = 0
        for bill in upcoming_bills:
            tenant = bill.tenant
            recipient_email = test_email_recipient if test_email_recipient else tenant.email

            subject = render_to_string('billing/email/upcoming_due_reminder_subject.txt', {'bill': bill}).strip()
            body = render_to_string('billing/email/upcoming_due_reminder_body.txt', {'bill': bill, 'tenant': tenant})

            self.stdout.write(f"  - Upcoming: Bill ID {bill.id} for {tenant.full_name} ({recipient_email}), Due: {bill.due_date}")
            if not dry_run:
                try:
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient_email])
                    sent_upcoming_count += 1
                    # Optionally, add a field to Bill like `last_upcoming_reminder_sent_at` and update it.
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"    Error sending upcoming reminder for Bill ID {bill.id}: {e}"))
            else:
                self.stdout.write(self.style.NOTICE(f"    (Dry run) Would send upcoming reminder for Bill ID {bill.id} to {recipient_email}"))


        # --- Overdue Bill Reminders ---
        overdue_bills = Bill.objects.filter(
            is_paid=False,
            due_date__lt=today, # Due date is in the past
            tenant__is_active=True,
            tenant__email__isnull=False
        ).exclude(tenant__email__exact='').select_related('tenant') # Optimize tenant query
        # Note: This will send for ALL overdue bills daily without more advanced logic (e.g., `last_overdue_reminder_sent_at` field on Bill)

        self.stdout.write(f"Found {overdue_bills.count()} overdue bill(s) as of {today}.")
        sent_overdue_count = 0
        for bill in overdue_bills:
            tenant = bill.tenant
            recipient_email = test_email_recipient if test_email_recipient else tenant.email

            subject = render_to_string('billing/email/overdue_bill_reminder_subject.txt', {'bill': bill}).strip()
            body = render_to_string('billing/email/overdue_bill_reminder_body.txt', {'bill': bill, 'tenant': tenant})

            self.stdout.write(f"  - Overdue: Bill ID {bill.id} for {tenant.full_name} ({recipient_email}), Due: {bill.due_date}")
            if not dry_run:
                try:
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient_email])
                    sent_overdue_count += 1
                    # Optionally, update `Bill.last_overdue_reminder_sent_at`
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"    Error sending overdue reminder for Bill ID {bill.id}: {e}"))
            else:
                self.stdout.write(self.style.NOTICE(f"    (Dry run) Would send overdue reminder for Bill ID {bill.id} to {recipient_email}"))


        self.stdout.write(self.style.SUCCESS(
            f"Reminder processing complete. Sent {sent_upcoming_count} upcoming reminders and {sent_overdue_count} overdue reminders."
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("This was a dry run. No emails were actually sent."))
