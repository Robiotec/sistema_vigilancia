from django.db import models

from apps.core.models import LegacyTimestampMixin, LegacyUuidModel
from apps.organizations.models import Company


class Role(LegacyTimestampMixin, LegacyUuidModel):
    name = models.CharField(max_length=40)
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "roles"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class LegacyUser(LegacyTimestampMixin, LegacyUuidModel):
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="users",
    )
    username = models.CharField(max_length=80)
    email = models.EmailField(max_length=180, null=True, blank=True)
    name = models.CharField(max_length=160, null=True, blank=True)
    password_hash = models.CharField(max_length=255)
    active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "users"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.name or self.username


class UserRole(models.Model):
    user_id = models.UUIDField(primary_key=True, db_column="user_id")
    role = models.ForeignKey(
        Role,
        db_column="role_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="user_links",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "user_roles"
        unique_together = [("user_id", "role")]

    @property
    def legacy_user(self) -> LegacyUser | None:
        return LegacyUser.all_objects.filter(id=self.user_id).first()
