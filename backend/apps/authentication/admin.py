"""Admin for user profiles, plus a User page that shows what a user owns.

Django's stock User admin is replaced rather than extended so an administrator
looking at an account can see, on that account's page, how many documents and
conversations it owns — which is the question they are actually there to answer,
and the one that decides whether deleting the account is safe.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Role, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('email_verified', 'document_quota', 'last_active_at', 'role_display')
    readonly_fields = ('last_active_at', 'role_display')

    @admin.display(description='Role')
    def role_display(self, obj):
        return obj.role if obj.pk else '—'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role_badge', 'email_verified', 'document_quota',
                    'last_active_at', 'created_at')
    list_filter = ('email_verified', 'created_at')
    search_fields = ('user__username', 'user__email', 'user__first_name')
    raw_id_fields = ('user',)
    list_select_related = ('user',)
    readonly_fields = ('created_at', 'updated_at', 'role_badge')

    @admin.display(description='Role')
    def role_badge(self, obj):
        colours = {
            Role.SUPERADMIN: ('#7c2d12', '#ffedd5'),
            Role.ADMIN: ('#5b21b6', '#ede9fe'),
            Role.USER: ('#374151', '#e5e7eb'),
        }
        fg, bg = colours[obj.role]
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:10px;'
            'font-size:11px;font-weight:600;color:{};background:{};">{}</span>',
            fg, bg, obj.role,
        )


class RagUserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'first_name', 'is_active', 'is_staff',
                    'document_total', 'conversation_total', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    inlines = [UserProfileInline]
    readonly_fields = ('owned_content',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _documents=Count('documents', distinct=True),
            _conversations=Count('conversations', distinct=True),
        )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        return tuple(fieldsets) + (('Owned content', {'fields': ('owned_content',)}),)

    @admin.display(description='Documents', ordering='_documents')
    def document_total(self, obj):
        return obj._documents

    @admin.display(description='Chats', ordering='_conversations')
    def conversation_total(self, obj):
        return obj._conversations

    @admin.display(description='Owned content')
    def owned_content(self, obj):
        """Links to everything that a cascade would take with this account."""
        docs_url = reverse('admin:documents_document_changelist')
        convs_url = reverse('admin:chat_conversation_changelist')
        return mark_safe(  # noqa: S308 - reversed URLs and integers, not user input
            f'<a href="{docs_url}?owner__id__exact={obj.pk}">'
            f'{obj.documents.count()} document(s)</a> &nbsp;·&nbsp; '
            f'<a href="{convs_url}?owner__id__exact={obj.pk}">'
            f'{obj.conversations.count()} conversation(s)</a>'
            '<p style="color:#b91c1c;margin-top:8px;">Deleting this account '
            'deletes all of the above, including its uploaded files\' database '
            'rows and every chunk and embedding derived from them.</p>'
        )


admin.site.unregister(User)
admin.site.register(User, RagUserAdmin)

# The admin is an operator console for this project, not a generic Django site.
admin.site.site_header = 'RAG Chatbot administration'
admin.site.site_title = 'RAG Chatbot admin'
admin.site.index_title = 'Operations'
