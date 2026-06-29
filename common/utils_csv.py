import csv
import io
from django.http import HttpResponse


def generate_csv_response(filename, headers, rows):
    """
    Returns an HttpResponse with CSV content.
    `headers` - list of column header strings
    `rows`    - list of lists/tuples with row data
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def parse_csv_from_request(request, required_fields=None):
    """
    Reads an uploaded CSV file from request.FILES['file'] and
    returns (headers, rows_as_dicts, error_string).
    """
    if 'file' not in request.FILES:
        return None, None, "No file uploaded. Send the CSV under the key 'file'."

    uploaded = request.FILES['file']
    if not uploaded.name.endswith('.csv'):
        return None, None, "Invalid file type. Only .csv files are accepted."

    try:
        text = uploaded.read().decode('utf-8-sig')  # utf-8-sig strips BOM if present
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        rows = list(reader)
    except Exception as e:
        return None, None, f"Failed to parse CSV: {str(e)}"

    if required_fields:
        missing = [f for f in required_fields if f not in headers]
        if missing:
            return None, None, f"Missing required columns: {', '.join(missing)}"

    return headers, rows, None
