# -*- coding: utf-8 -*-
from django.contrib import admin
from flash.models import *
from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin

admin.site.unregister(User)


class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_staff', 'is_active',)
    list_filter = ('is_staff', 'is_superuser', 'is_active',)

admin.site.register(User, CustomUserAdmin)


class ScreenshotInline(admin.StackedInline):
    model = Screenshot


class FlashAdmin(admin.ModelAdmin):
    date_hierarchy = 'publication_date'
    fieldsets = (
        (None, {
            'fields': ('name', 'description',  'theme', 'game_type',
                       'flashfile', 'thumbfile', 'filesize',)
        }),
        ('Advanced options', {
            'classes': ('collapse',),
            'fields': ('rate', 'views', 'active', 'publication_date',
                       'get_preview',)
        }),
    )
    readonly_fields = ('get_preview', )
    list_display = ('name',  'flashfile', 'gthumb', 'is_flash_exist',
                    'game_type', 'user', 'rate', 'views',  'publication_date', )
    list_filter = ('theme', 'rate', 'publication_date', 'active')
    search_fields = ('name', "flashfile",)
    ordering = ('-publication_date', )
    inlines = [ScreenshotInline, ]


class ThemeAdmin(admin.ModelAdmin):
    pass


class CommentAdmin(admin.ModelAdmin):
    search_fields = ('text',)
    list_display = ("text", "publication_date")
    date_hierarchy = 'publication_date'

admin.site.register(Comment, CommentAdmin)


class ProfileAdmin(admin.ModelAdmin):
    pass


class BanAdmin(admin.ModelAdmin):
    list_display = ("ip", "publication_date",)
    search_fields = ("ip", )
    ordering = ('-publication_date', )


class BannedWordAdmin(admin.ModelAdmin):
    list_display = ("word", "publication_date",)
    search_fields = ("word", )
    ordering = ('-publication_date', )


class SearchAdmin(admin.ModelAdmin):
    list_display = ("query", "count")
    search_fields = ("query", )

admin.site.register(Flash,   FlashAdmin)
admin.site.register(Theme,   ThemeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Ban, BanAdmin)
admin.site.register(BannedWord, BannedWordAdmin)

admin.site.register(Search, SearchAdmin)
