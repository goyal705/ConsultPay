from rest_framework.permissions import BasePermission


class IsUser(BasePermission):
    message = "Only users can do this."

    def has_permission(self, request, view):
        return request.user.is_authenticated and not request.user.is_provider


class IsProvider(BasePermission):
    message = "Only providers can do this."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_provider
