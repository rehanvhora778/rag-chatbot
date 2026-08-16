from rest_framework import serializers


class CreateSessionSerializer(serializers.Serializer):
    title        = serializers.CharField(max_length=200, required=True)
    document_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        min_length=1,
    )


class UpdateSessionSerializer(serializers.Serializer):
    title    = serializers.CharField(max_length=200, required=False)
    status   = serializers.ChoiceField(choices=['active', 'archived'], required=False)
    # Swapping the documents a conversation is grounded in. Ownership and
    # processing state are re-checked in the view, exactly as on create.
    document_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        min_length=1,
        required=False,
    )


class SendMessageSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=1, max_length=4000)
