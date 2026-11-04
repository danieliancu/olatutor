from django.db import migrations

CREATE = """
CREATE TRIGGER manualtranscription_append_only BEFORE UPDATE OR DELETE ON grading_manualtranscription
    FOR EACH ROW EXECUTE FUNCTION notebooks_block_update();
CREATE TRIGGER verification_append_only BEFORE UPDATE OR DELETE ON grading_verification
    FOR EACH ROW EXECUTE FUNCTION notebooks_block_update();
"""

DROP = """
DROP TRIGGER manualtranscription_append_only ON grading_manualtranscription;
DROP TRIGGER verification_append_only ON grading_verification;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("grading", "0001_initial"),
        ("notebooks", "0002_append_only_triggers"),
    ]
    operations = [migrations.RunSQL(CREATE, DROP)]
