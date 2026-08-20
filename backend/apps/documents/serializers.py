from django.conf import settings
from rest_framework import serializers

from core.utils import get_file_extension


class DocumentUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        max_length=10,
    )

    def validate_files(self, files):
        errors = []
        allowed = ', '.join(settings.ALLOWED_DOCUMENT_EXTENSIONS)
        limit_mb = settings.MAX_DOCUMENT_SIZE_MB

        for f in files:
            ext = get_file_extension(f.name)
            if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
                errors.append(f"{f.name}: unsupported type. Allowed: {allowed}.")
            elif f.size > limit_mb * 1024 * 1024:
                errors.append(f"{f.name}: exceeds {limit_mb}MB limit.")

        if errors:
            raise serializers.ValidationError(errors)
        return files


class RenameDocumentSerializer(serializers.Serializer):
    original_filename = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_original_filename(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name cannot be empty.')
        # A rename is a label change, not a move — reject anything that looks
        # like a path so the stored name can never escape its directory.
        if any(ch in value for ch in ('/', '\\', '\0')):
            raise serializers.ValidationError('Name cannot contain path separators.')
        return value


class DocumentSerializer(serializers.Serializer):
    id              = serializers.CharField()
    original_filename = serializers.CharField()
    file_type       = serializers.CharField()
    file_size       = serializers.IntegerField()
    status          = serializers.CharField()
    page_count      = serializers.IntegerField(default=0)
    word_count      = serializers.IntegerField(default=0)
    chunk_count     = serializers.IntegerField(default=0)
    summary         = serializers.CharField(default='', allow_blank=True)
    error_message   = serializers.CharField(default='', allow_blank=True)
    created_at      = serializers.DateTimeField()
    updated_at      = serializers.DateTimeField()
