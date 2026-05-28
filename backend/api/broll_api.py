# -*- coding: utf-8 -*-
"""字幕驱动自动补画面 API。"""

import logging
from flask import jsonify, request

from backend.services.broll_service import BrollService

logger = logging.getLogger(__name__)


def register_broll_routes(app, db_manager, socketio=None):
    """注册补画面业务 API。"""
    service = BrollService(db_manager, socketio)

    @app.route('/api/broll/session/<project_id>', methods=['GET'])
    def get_broll_session(project_id):
        try:
            session = service.get_session(project_id)
            return jsonify({'code': 0, 'msg': '获取补画面工作区成功', 'data': session})
        except ValueError as e:
            return jsonify({'code': 1, 'msg': str(e), 'data': None}), 404
        except Exception as e:
            logger.error(f'获取补画面工作区失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'获取补画面工作区失败: {e}', 'data': None}), 500

    @app.route('/api/broll/session/<project_id>', methods=['POST'])
    def save_broll_session(project_id):
        try:
            data = request.get_json() or {}
            session = service.save_session(project_id, data)
            return jsonify({'code': 0, 'msg': '补画面工作区已保存', 'data': session})
        except ValueError as e:
            return jsonify({'code': 1, 'msg': str(e), 'data': None}), 404
        except Exception as e:
            logger.error(f'保存补画面工作区失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'保存补画面工作区失败: {e}', 'data': None}), 500

    @app.route('/api/broll/providers', methods=['GET'])
    def get_broll_providers():
        try:
            return jsonify({'code': 0, 'msg': '获取素材源状态成功', 'data': service.get_provider_status()})
        except Exception as e:
            logger.error(f'获取素材源状态失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'获取素材源状态失败: {e}', 'data': None}), 500

    @app.route('/api/broll/plan-task', methods=['POST'])
    def create_broll_plan_task():
        return _create_task_response(service.create_plan_task, '补画面方案任务已创建')

    @app.route('/api/broll/search-task', methods=['POST'])
    def create_broll_search_task():
        return _create_task_response(service.create_search_task, '素材搜索任务已创建')

    @app.route('/api/broll/download-task', methods=['POST'])
    def create_broll_download_task():
        return _create_task_response(service.create_download_task, '素材下载任务已创建')

    @app.route('/api/broll/compose-task', methods=['POST'])
    def create_broll_compose_task():
        return _create_task_response(service.create_compose_task, '补画面合成任务已创建')

    @app.route('/api/broll/license-manifest/<project_id>', methods=['GET'])
    def get_broll_license_manifest(project_id):
        try:
            manifest = service.export_license_manifest(project_id)
            return jsonify({'code': 0, 'msg': '素材来源清单已生成', 'data': manifest})
        except ValueError as e:
            return jsonify({'code': 1, 'msg': str(e), 'data': None}), 404
        except Exception as e:
            logger.error(f'生成素材来源清单失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'生成素材来源清单失败: {e}', 'data': None}), 500

    def _create_task_response(factory, success_msg):
        try:
            data = request.get_json() or {}
            task_id = factory(data)
            return jsonify({
                'code': 0,
                'msg': success_msg,
                'data': {
                    'task_id': task_id,
                    'project_id': data.get('project_id')
                }
            })
        except ValueError as e:
            return jsonify({'code': 1, 'msg': str(e), 'data': None}), 400
        except Exception as e:
            logger.error(f'{success_msg}失败: {e}', exc_info=True)
            return jsonify({'code': 1, 'msg': f'{success_msg}失败: {e}', 'data': None}), 500

    logger.info('✅ 补画面 API 路由注册完成')
