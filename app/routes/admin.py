from flask import Blueprint, render_template
from app.extensions import scheduler

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/jobs')
def view_jobs():
    jobs = scheduler.get_jobs()
    return render_template('admin/jobs.html', jobs=jobs)
