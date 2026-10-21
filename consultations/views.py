from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import ConsultationSession
from .serializers import AssignSerializer, CancelSerializer, CreateSessionSerializer, SessionSerializer


class SessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SessionSerializer

    def get_queryset(self):
        user = self.request.user
        return ConsultationSession.objects.filter(Q(user=user) | Q(provider=user)).select_related("user", "provider")

    def _run(self, fn, *args, **kwargs):
        try:
            session = fn(*args, **kwargs)
        except services.NotAllowed as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except services.SessionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SessionSerializer(session).data)

    def create(self, request):
        serializer = CreateSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = self._run(services.create_session, request.user, serializer.validated_data.get("provider_id"))
        if response.status_code == 200:
            response.status_code = status.HTTP_201_CREATED
        return response

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(services.assign, self.get_object(), request.user, serializer.validated_data["provider_id"])

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._run(services.accept, self.get_object(), request.user)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._run(services.start, self.get_object(), request.user)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        return self._run(services.end, self.get_object(), request.user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(services.cancel, self.get_object(), request.user, serializer.validated_data.get("reason", ""))

    @action(detail=True, methods=["post"])
    def bill(self, request, pk=None):
        return self._run(services.bill, self.get_object())
