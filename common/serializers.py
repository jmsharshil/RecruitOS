from rest_framework import serializers
from datetime import datetime
from django.utils.dateparse import parse_date, parse_datetime
from dateutil.parser import parse as parse_dateutil


class DateParserField(serializers.DateField):
    """
    Flexible date parser supporting multiple formats via dateutil.parser.parse(fuzzy=True)
    + explicit fallback formats. Used for all DateFields to support CSV/Excel imports,
    varied user input, and natural language dates where possible.
    Raises ValidationError with helpful message on failure.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault('input_formats', [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y',
            '%Y/%m/%d', '%d.%m.%Y', '%m.%d.%Y', '%d %b %Y', '%d %B %Y',
            '%b %d, %Y', '%B %d, %Y',
        ])
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if not data:
                return None
            try:
                # Primary robust parser with fuzzy=True for flexibility (CSV, Excel, natural lang)
                parsed = parse_dateutil(data, fuzzy=True)
                if parsed:
                    return parsed.date() if hasattr(parsed, 'date') else parsed
            except (ValueError, TypeError, OverflowError):
                pass
            # Fallback to django and explicit formats
            parsed = parse_date(data)
            if parsed:
                return parsed
            for fmt in self.input_formats:
                try:
                    return datetime.strptime(data, fmt).date()
                except ValueError:
                    continue
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            raise serializers.ValidationError(
                "Invalid date format. Please use YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, "
                "or other common formats."
            ) from None


class DateParserDateTimeField(serializers.DateTimeField):
    """
    Flexible datetime parser using dateutil.parser.parse(fuzzy=True) + format fallbacks.
    Supports CSV/Excel imports with various datetime strings.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault('input_formats', [
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M',
            '%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M',
        ])
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if not data:
                return None
            try:
                # Primary: dateutil fuzzy parse
                parsed = parse_dateutil(data, fuzzy=True)
                if parsed:
                    return parsed
            except (ValueError, TypeError, OverflowError):
                pass
            # Fallbacks
            parsed = parse_datetime(data)
            if parsed:
                return parsed
            for fmt in self.input_formats:
                try:
                    return datetime.strptime(data, fmt)
                except ValueError:
                    continue
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            raise serializers.ValidationError(
                "Invalid datetime format. Please use ISO or common formats like YYYY-MM-DD HH:MM."
            ) from None
