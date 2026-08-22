from rest_framework import serializers


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


