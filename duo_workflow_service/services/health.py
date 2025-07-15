from contract import health_pb2, health_pb2_grpc


# pylint: disable=invalid-overridden-method
class HealthService(health_pb2_grpc.HealthServicer):
    async def Check(self, request, context) -> health_pb2.HealthCheckResponse:
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.ServingStatus.SERVING
        )


# pylint: enable=invalid-overridden-method
