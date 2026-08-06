# backend/api_response.py
"""Padrão de resposta de API consistente."""
from flask import jsonify
from typing import Any, Dict, Optional, List


class ApiResponse:
    """Gerenciador de respostas da API com envelope padrão."""
    
    @staticmethod
    def success(data: Any = None, message: str = "Sucesso", status_code: int = 200) -> tuple:
        """Retorna resposta de sucesso."""
        response = {
            "status": "success",
            "code": status_code,
            "message": message,
            "data": data,
        }
        return jsonify(response), status_code
    
    @staticmethod
    def error(
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[Any] = None,
        status_code: int = 400
    ) -> tuple:
        """Retorna resposta de erro."""
        response = {
            "status": "error",
            "code": status_code,
            "error_code": code,
            "message": message,
        }
        if details:
            response["details"] = details
        return jsonify(response), status_code
    
    @staticmethod
    def created(data: Any = None, message: str = "Criado com sucesso") -> tuple:
        """Retorna resposta 201 Created."""
        return ApiResponse.success(data, message, 201)
    
    @staticmethod
    def no_content() -> tuple:
        """Retorna resposta 204 No Content."""
        return "", 204
    
    @staticmethod
    def not_found(message: str = "Recurso não encontrado") -> tuple:
        """Retorna resposta 404 Not Found."""
        return ApiResponse.error(message, "NOT_FOUND", None, 404)
    
    @staticmethod
    def unauthorized(message: str = "Não autorizado") -> tuple:
        """Retorna resposta 401 Unauthorized."""
        return ApiResponse.error(message, "UNAUTHORIZED", None, 401)
    
    @staticmethod
    def forbidden(message: str = "Acesso proibido") -> tuple:
        """Retorna resposta 403 Forbidden."""
        return ApiResponse.error(message, "FORBIDDEN", None, 403)
    
    @staticmethod
    def validation_error(details: Dict[str, List[str]]) -> tuple:
        """Retorna resposta 422 Unprocessable Entity."""
        return ApiResponse.error(
            "Erro de validação",
            "VALIDATION_ERROR",
            details,
            422
        )
    
    @staticmethod
    def server_error(
        message: str = "Erro interno do servidor",
        correlation_id: Optional[str] = None
    ) -> tuple:
        """Retorna resposta 500 Internal Server Error."""
        details = {}
        if correlation_id:
            details["correlation_id"] = correlation_id
        return ApiResponse.error(
            message,
            "INTERNAL_SERVER_ERROR",
            details if details else None,
            500
        )
    
    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 10,
        message: str = "Sucesso"
    ) -> tuple:
        """Retorna resposta paginada."""
        response = {
            "status": "success",
            "code": 200,
            "message": message,
            "data": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size,
            }
        }
        return jsonify(response), 200
