# jobs/models.py
from django.db import models
from django.utils import timezone
from inventory.models import InventoryItem , ProductCategory
import uuid # We'll use this to generate unique ticket numbers




class Customer(models.Model):
    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Contract(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='contract')
    items = models.ManyToManyField(ProductCategory, related_name='contracts', blank=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    def __str__(self): return f"Contract for {self.customer.name}"

class Job(models.Model):
    JOB_TYPE_CHOICES = [
        ('1101', '1101 (Fishing)'),
        ('1102', '1102 (Rental)'),
        ('1103', '1103 (Jars)'),
        ('1104', '1104 (Machine shop)'),
    ]
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed')]
    
    # NEW: The job type prefix, chosen by the user
    job_type = models.CharField(max_length=4, choices=JOB_TYPE_CHOICES)
    job_number = models.CharField(max_length=50, unique=True, blank=True, editable=False)
    
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='jobs')

    rig = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    well = models.CharField(max_length=100)
    trans = models.CharField(max_length=100, blank=True, null=True, verbose_name="Transportation")
    date = models.DateField(default=timezone.now)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # The old job_name and the simple job_number are now removed

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.job_number if self.job_number else "New Job"

    def save(self, *args, **kwargs):
        # This logic only runs when the job is first created
        if not self.pk: 
            # Find the last job of the same type
            last_job = Job.objects.filter(job_type=self.job_type).order_by('id').last()
            if last_job:
                # Extract the counter, increment, and format
                last_counter = int(last_job.job_number.split('-')[-1])
                new_counter = last_counter + 1
            else:
                # This is the first job of this type
                new_counter = 1
            
            # Format the new job number (e.g., 1101-001)
            self.job_number = f"{self.job_type}-{new_counter:03d}"
        
        super().save(*args, **kwargs)
    

class DeliveryTicket(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='delivery_tickets')
    ticket_number = models.CharField(max_length=100, blank=True) # Removed unique=True for now
    ticket_date = models.DateTimeField(auto_now_add=True)
    items = models.ManyToManyField(InventoryItem, related_name='delivery_tickets')

    class Meta:
        # This ensures that a ticket number is unique FOR A GIVEN JOB
        unique_together = ('job', 'ticket_number')

    def __str__(self):
        return self.ticket_number

    def save(self, *args, **kwargs):
        if not self.pk: # Only generate number for new tickets
            # --- THE FIX IS HERE: We filter by 'job=self.job' ---
            last_ticket = DeliveryTicket.objects.filter(job=self.job).order_by('id').last()
            
            new_num = 1
            if last_ticket and last_ticket.ticket_number:
                try:
                    last_num = int(last_ticket.ticket_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1 # Fallback if parsing fails
            
            self.ticket_number = f"DT-{new_num:03d}"
        
        super().save(*args, **kwargs)

class ReceivingTicket(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='receiving_tickets')
    ticket_number = models.CharField(max_length=100, blank=True)
    ticket_date = models.DateTimeField(auto_now_add=True)
    items = models.ManyToManyField(InventoryItem, related_name='receiving_tickets')

    class Meta:
        unique_together = ('job', 'ticket_number')

    def __str__(self):
        return self.ticket_number

    def save(self, *args, **kwargs):
        if not self.pk:
            # --- THE FIX IS HERE: We filter by 'job=self.job' ---
            last_ticket = ReceivingTicket.objects.filter(job=self.job).order_by('id').last()
            
            new_num = 1
            if last_ticket and last_ticket.ticket_number:
                try:
                    last_num = int(last_ticket.ticket_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            
            self.ticket_number = f"RT-{new_num:03d}"
            
        super().save(*args, **kwargs)
    

class JobAttachment(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='attachments')
    file = models.ImageField(upload_to='job_attachments/')
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.job.job_number} uploaded on {self.uploaded_at.strftime('%Y-%m-%d')}"
    


