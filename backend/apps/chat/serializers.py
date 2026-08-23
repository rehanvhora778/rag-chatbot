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


class FeedbackSerializer(serializers.Serializer):
    """A verdict on one assistant answer.

    `rating` is an integer rather than a boolean so a future "neutral" or a
    finer scale does not require a migration of every stored row.
    """

    rating = serializers.ChoiceField(choices=[1, -1])
    # Only meaningful on a negative rating; the service clears it on a positive
    # one, since every option describes a way the answer was wrong.
    reason = serializers.ChoiceField(
        choices=['incorrect', 'irrelevant', 'missing', 'hallucination', 'other'],
        required=False, allow_blank=True, default='',
    )
    comment = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default='',
    )
