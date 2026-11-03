from django.db import migrations

CREATE = """
CREATE FUNCTION notebooks_block_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inkoperation_append_only BEFORE UPDATE ON notebooks_inkoperation
    FOR EACH ROW EXECUTE FUNCTION notebooks_block_update();
CREATE TRIGGER pagerevision_append_only BEFORE UPDATE ON notebooks_pagerevision
    FOR EACH ROW EXECUTE FUNCTION notebooks_block_update();
"""

DROP = """
DROP TRIGGER inkoperation_append_only ON notebooks_inkoperation;
DROP TRIGGER pagerevision_append_only ON notebooks_pagerevision;
DROP FUNCTION notebooks_block_update();
"""


class Migration(migrations.Migration):
    dependencies = [("notebooks", "0001_initial")]
    operations = [migrations.RunSQL(CREATE, DROP)]
