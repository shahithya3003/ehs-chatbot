from django.urls import path
# Import the new class-based view
from .views import ChatbotAPIView

urlpatterns = [
    path('', ChatbotAPIView.as_view(), name='chatbot_api'), # Use .as_view() for class-based views
]