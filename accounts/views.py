from django.contrib.auth import get_user_model
from rest_framework import generics, permissions
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

from .serializers import ProviderSerializer, RegisterSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = Token.objects.create(user=user)
        return Response({**serializer.data, "token": token.key}, status=201)


class ProviderListView(generics.ListAPIView):
    serializer_class = ProviderSerializer
    queryset = User.objects.filter(role=User.Role.PROVIDER).order_by("username")
