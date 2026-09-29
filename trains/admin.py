from django.contrib import admin

from .models import Line, Station, StopTime, Train, TrainRun


@admin.register(Line)
class LineAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "color")


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Train)
class TrainAdmin(admin.ModelAdmin):
    list_display = ("number", "line", "category", "origin", "destination", "tracked")
    list_filter = ("line", "tracked")
    search_fields = ("number",)


class StopInline(admin.TabularInline):
    model = StopTime
    extra = 0


@admin.register(TrainRun)
class TrainRunAdmin(admin.ModelAdmin):
    list_display = ("train", "service_date", "cancelled", "updated_at")
    list_filter = ("service_date", "train__line")
    inlines = [StopInline]
