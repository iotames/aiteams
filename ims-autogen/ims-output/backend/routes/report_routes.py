"""报表统计路由"""

from flask import Blueprint, request
from services.report_service import ReportService
from utils.response import success_response, error_response

report_bp = Blueprint('report', __name__, url_prefix='/api/v1')


@report_bp.route('/reports/summary', methods=['GET'])
def get_summary_report():
    """获取进销存汇总报表"""
    start_date = request.args.get('start_date', '').strip() or None
    end_date = request.args.get('end_date', '').strip() or None

    try:
        report = ReportService.get_summary_report(start_date=start_date, end_date=end_date)
        return success_response(report)
    except Exception as e:
        return error_response(str(e))


@report_bp.route('/reports/sales-detail', methods=['GET'])
def get_sales_detail():
    """获取销售明细报表"""
    start_date = request.args.get('start_date', '').strip() or None
    end_date = request.args.get('end_date', '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        items, total = ReportService.get_sales_detail(
            start_date=start_date, end_date=end_date,
            page=page, per_page=per_page
        )
        return success_response({
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        })
    except Exception as e:
        return error_response(str(e))
