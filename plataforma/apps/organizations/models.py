from django.db import models

from apps.core.models import LegacyTimestampMixin, LegacyUuidModel


class Company(LegacyTimestampMixin, LegacyUuidModel):
    name = models.CharField(max_length=160)
    ruc = models.CharField(max_length=30, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Area(LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="areas",
    )
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "areas"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
