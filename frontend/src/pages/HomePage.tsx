import { HealthStatus } from '../components/ui/HealthStatus';

export function HomePage() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      <div className="max-w-3xl w-full flex flex-col items-center space-y-12">
        <div className="text-center space-y-4">
          <h1 className="text-6xl font-extrabold tracking-tight text-gray-900">
            Cloud<span className="text-blue-600">Vault</span>
          </h1>
          <p className="text-xl text-gray-500 font-light tracking-wide">
            AI-Native Cloud File Storage
          </p>
        </div>
        
        <div className="w-full max-w-md">
          <HealthStatus />
        </div>
      </div>
    </div>
  );
}
